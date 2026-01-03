import sys
import time
import logging
from logging.handlers import RotatingFileHandler

# 사용자 모듈 (기능별 분리)
import kis_scan
import mervis_brain
import mervis_ai
import mervis_state
import mervis_profile
import mervis_bigquery
import update_volume_tier
import kis_websocket
import kis_account

# [설정] 로깅 시스템 초기화 (콘솔 출력 방지 및 파일 저장)
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 초기화 (중복 방지)
    if logger.handlers:
        logger.handlers = []

    # 파일 핸들러 (모든 로그는 파일로 저장)
    # RotatingFileHandler: 파일 크기가 5MB 넘으면 백업하고 새 파일 생성 (최대 3개 유지)
    file_handler = RotatingFileHandler('mervis.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # *주의: 콘솔 핸들러(StreamHandler)는 추가하지 않음. 
    # 따라서 logging.info()로 찍는 내용은 터미널에 안 나옴 (UI 보호).

def system_init():
    print("==================================================")
    print(" [MERVIS] System Initialization")
    print("==================================================")
    
    # 1. 로깅 시작
    setup_logging()
    logging.info("System Start.")

    # 2. DB 상태 점검
    print(" [Check] Database Status...", end=" ")
    is_fresh = mervis_bigquery.check_db_freshness()
    
    if is_fresh:
        print("OK.")
        logging.info("DB is up-to-date.")
    else:
        print("UPDATE REQUIRED.")
        print(" [Process] Updating Volume Analysis Data...")
        logging.info("DB outdated. Starting update_volume_tier.")
        try:
            update_volume_tier.update_volume_data()
            print(" [Success] Database Updated.")
            logging.info("DB Update Complete.")
        except Exception as e:
            print(f" [Warning] Update Failed: {e}")
            logging.error(f"DB Update Failed: {e}")
            
    print("==================================================\n")

def run_system():
    # 1. 초기화 실행
    system_init()

    # 2. 모드 선택
    print(" [Select Mode]")
    print(" 1. REAL (Actual Trading)")
    print(" 2. MOCK (Simulation)")
    
    choice = input(" >> Select (1/2): ").strip()
    mervis_state.set_mode(choice)
    
    mode_name = "REAL" if mervis_state.is_real() else "MOCK"
    logging.info(f"Mode set to {mode_name}")
    print(f"\n [System] Mode: {mode_name}")

    # 3. 자산 동기화 (kis_account 연동)
    print(f" [Process] Syncing Asset Data ({mode_name})...")
    try:
        my_asset = kis_account.get_my_total_assets()
        
        if my_asset:
            # 출력 메시지 간소화
            print(f" -> Total Asset: ${my_asset['total']:,.2f}")
            print(f" -> PnL Rate   : {my_asset['pnl']}%")
            
            # DB 저장 (이력 관리)
            mervis_bigquery.save_daily_balance(
                total_asset=my_asset['total'],
                cash=my_asset['cash'],
                stock_val=my_asset['stock'],
                pnl_daily=my_asset['pnl']
            )
            logging.info(f"Asset Synced: Total=${my_asset['total']}, PnL={my_asset['pnl']}%")
        else:
            print(" -> [Warning] Failed to fetch asset data.")
            logging.warning("Asset fetch failed.")

    except Exception as e:
        print(f" -> [Error] Asset Sync Error: {e}")
        logging.error(f"Asset Sync Error: {e}")

    # 4. 메인 루프
    while True:
        # 현재 백그라운드 감시 상태 확인
        ws_active = kis_websocket.is_active()
        status_text = "RUNNING" if ws_active else "STOPPED"

        print(f"\n==================================================")
        print(f" [MENU] Monitoring: {status_text}")
        print(f"==================================================")
        print(" 1. Auto Scan (Full Market)")
        print(" 2. Sniper Search (Specific Ticker)")
        print(" 3. Free Talk (AI Assistant)")
        print(" 4. Exit")
        
        if ws_active:
            print(" 5. Stop Background Monitoring")
        else:
            print(" 5. Start Background Monitoring")
        
        menu = input(" >> Input: ").strip()
        
        # 메뉴 처리
        if menu == '1':
            logging.info("User started Auto Scan.")
            try:
                # DB에서 상위 종목 호출
                targets = mervis_bigquery.get_tickers_from_db(limit=40) 
                print(f"\n [Mervis] Scanning {len(targets)} tickers...")
                
                results = []
                for i, item in enumerate(targets):
                    # 진행률 표시
                    print(f"\r [{i+1}/{len(targets)}] Analyzing {item['code']}...", end="")
                    sys.stdout.flush()
                    
                    # 뇌(Brain) 모듈 호출
                    res = mervis_brain.analyze_stock(item)
                    if res:
                        results.append(res)
                
                print("\n [Done] Analysis Complete.")
                
                if results:
                    report_text = f"[{mode_name} Scan Report]\n"
                    for r in results:
                        report_text += f"[{r['code']}] {r['report']}\n"
                    
                    # AI에게 결과 전달
                    mervis_ai.start_consulting(report_text)
                    
            except KeyboardInterrupt:
                print("\n [Stop] Scan cancelled by user.")
                logging.info("Auto Scan cancelled.")

        elif menu == '2':
            code = input(" >> Ticker: ").upper().strip()
            if code:
                logging.info(f"User searched ticker: {code}")
                print(f" [Mervis] Analyzing '{code}'...")
                
                # 단일 종목 분석용 임시 데이터 구조
                target_item = {"code": code, "name": "Manual", "price": 0}
                res = mervis_brain.analyze_stock(target_item)
                
                if res:
                    print(" -> Analysis Complete.")
                    mervis_ai.start_consulting(f"[Sniper Report]\n{res['report']}")
                else:
                    print(" -> No significant data found or error.")

        elif menu == '3':
            logging.info("Entered Free Talk mode.")
            print(" [Mervis] Conversation Mode. (Type 'exit' to return)")
            
            # AI에게 현재 시스템 상태 컨텍스트 주입
            context = f"[System Info] Mode: {mode_name}, Monitor: {status_text}"
            
            # AI 대화 루프 진입
            act = mervis_ai.start_consulting(context)
            
            if act == "EXIT":
                print(" [System] Terminating program.")
                sys.exit(0)

        elif menu == '4':
            logging.info("User requested exit.")
            if kis_websocket.is_active():
                kis_websocket.stop_monitoring()
            print(" [System] Shutdown.")
            sys.exit(0)

        elif menu == '5':
            if ws_active:
                print(" [Process] Stopping background monitoring...")
                kis_websocket.stop_monitoring()
                logging.info("Monitoring stopped.")
            else:
                print(" [Process] Starting background monitoring...")
                targets = mervis_bigquery.get_tickers_from_db(limit=40)
                if targets:
                    kis_websocket.start_background_monitoring(targets)
                    logging.info(f"Monitoring started for {len(targets)} tickers.")
                    print(" [Notice] Logs are saved to 'mervis.log'. Console will remain clean.")
                else:
                    print(" [Error] No targets found. Please run Scan (1) first or update DB.")

        else:
            print(" [Warning] Invalid Input.")

if __name__ == "__main__":
    run_system()