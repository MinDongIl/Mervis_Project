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

# [설정] 로깅 시스템 초기화
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        logger.handlers = []

    file_handler = RotatingFileHandler('mervis.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def system_init():
    print("==================================================")
    print(" [MERVIS] 시스템 초기화 중...")
    print("==================================================")
    
    setup_logging()
    logging.info("System Start.")

    print(" [Check] 데이터베이스 상태 점검...", end=" ")
    is_fresh = mervis_bigquery.check_db_freshness()
    
    if is_fresh:
        print("최신 상태입니다.")
        logging.info("DB is up-to-date.")
    else:
        print("업데이트 필요.")
        print(" [Process] 거래량 분석 데이터 갱신 중...")
        logging.info("DB outdated. Starting update_volume_tier.")
        try:
            update_volume_tier.update_volume_data()
            print(" [Success] DB 업데이트 완료.")
            logging.info("DB Update Complete.")
        except Exception as e:
            print(f" [Warning] 업데이트 실패: {e}")
            logging.error(f"DB Update Failed: {e}")
            
    print("==================================================\n")

def run_system():
    # 1. 초기화 실행
    system_init()

    # 2. 모드 선택
    print(" [모드 선택]")
    print(" 1. 실전 투자 (REAL)")
    print(" 2. 모의 투자 (MOCK)")
    
    choice = input(" >> 선택 (1/2): ").strip()
    mervis_state.set_mode(choice)
    
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    logging.info(f"Mode set to {mode_name}")
    print(f"\n [System] {mode_name} 모드로 시작합니다.")

    # 3. 자산 동기화
    print(f" [Process] 자산 현황 동기화 중 ({mode_name})...")
    try:
        my_asset = kis_account.get_my_total_assets()
        
        if my_asset:
            print(f" -> 총 자산: ${my_asset['total']:,.2f}")
            print(f" -> 수익률  : {my_asset['pnl']}%")
            
            mervis_bigquery.save_daily_balance(
                total_asset=my_asset['total'],
                cash=my_asset['cash'],
                stock_val=my_asset['stock'],
                pnl_daily=my_asset['pnl']
            )
            logging.info(f"Asset Synced: Total=${my_asset['total']}, PnL={my_asset['pnl']}%")
        else:
            print(" -> [Warning] 자산 데이터 조회 실패.")
            logging.warning("Asset fetch failed.")

    except Exception as e:
        print(f" -> [Error] 자산 동기화 오류: {e}")
        logging.error(f"Asset Sync Error: {e}")

    # 4. 메인 루프
    while True:
        # 현재 백그라운드 감시 상태 확인
        ws_active = kis_websocket.is_active()
        status_text = "가동 중 (ON)" if ws_active else "중지됨 (OFF)"

        print(f"\n==================================================")
        print(f" [메인 메뉴] 실시간 감시: {status_text}")
        print(f"==================================================")
        print(" 1. 전체 시장 자동 스캔 (Auto Scan)")
        print(" 2. 특정 종목 검색 (Sniper Search)")
        print(" 3. 대화 모드 (Free Talk)")
        print(" 4. 시스템 종료 (Exit)")
        
        if ws_active:
            print(" 5. 실시간 감시 중단")
        else:
            print(" 5. 실시간 감시 시작 (백그라운드)")
        
        menu = input(" >> 입력: ").strip()
        
        # 메뉴 처리
        if menu == '1':
            logging.info("User started Auto Scan.")
            try:
                targets = mervis_bigquery.get_tickers_from_db(limit=40) 
                print(f"\n [Mervis] 유망 종목 {len(targets)}개 스캔 시작...")
                
                results = []
                for i, item in enumerate(targets):
                    print(f"\r [{i+1}/{len(targets)}] '{item['code']}' 분석 중...", end="")
                    sys.stdout.flush()
                    
                    res = mervis_brain.analyze_stock(item)
                    if res:
                        results.append(res)
                
                print("\n [완료] 분석이 끝났습니다.")
                
                if results:
                    report_text = f"[{mode_name} 스캔 리포트]\n"
                    for r in results:
                        report_text += f"[{r['code']}] {r['report']}\n"
                    
                    # 스캔 후 자동으로 결과 상담 모드 진입
                    mervis_ai.start_consulting(report_text)
                    
            except KeyboardInterrupt:
                print("\n [중단] 사용자에 의해 취소되었습니다.")
                logging.info("Auto Scan cancelled.")

        elif menu == '2':
            code = input(" >> 종목 티커 입력: ").upper().strip()
            if code:
                logging.info(f"User searched ticker: {code}")
                print(f" [Mervis] '{code}' 정밀 분석 중...")
                
                target_item = {"code": code, "name": "Manual", "price": 0}
                res = mervis_brain.analyze_stock(target_item)
                
                if res:
                    print(" -> 분석 완료.")
                    mervis_ai.start_consulting(f"[Sniper Report]\n{res['report']}")
                else:
                    print(" -> 유의미한 데이터가 없거나 분석 실패.")

        elif menu == '3':
            logging.info("Entered Free Talk mode.")
            print(" [Mervis] 대화 모드입니다. (종료하려면 'q' 또는 'exit')")
            
            context = f"[System Info] Mode: {mode_name}, Monitor: {status_text}"
            
            act = mervis_ai.start_consulting(context)
            
            # [수정] EXIT 신호를 받으면 프로그램 종료가 아니라 메뉴로 복귀
            if act == "EXIT":
                print(" [시스템] 메인 메뉴로 돌아갑니다.")
                continue 

        elif menu == '4':
            logging.info("User requested exit.")
            if kis_websocket.is_active():
                kis_websocket.stop_monitoring()
            print(" [시스템] 프로그램을 종료합니다.")
            sys.exit(0)

        elif menu == '5':
            if ws_active:
                print(" [Process] 실시간 감시를 중단합니다...")
                kis_websocket.stop_monitoring()
                logging.info("Monitoring stopped.")
            else:
                print(" [Process] 백그라운드 감시를 시작합니다...")
                targets = mervis_bigquery.get_tickers_from_db(limit=40)
                if targets:
                    kis_websocket.start_background_monitoring(targets)
                    logging.info(f"Monitoring started for {len(targets)} tickers.")
                    print(" [알림] 로그는 'mervis.log'에 저장됩니다. 콘솔은 깨끗하게 유지됩니다.")
                else:
                    print(" [오류] 감시할 종목이 없습니다. 1번(스캔)을 먼저 실행하거나 DB를 업데이트하세요.")

        else:
            print(" [경고] 올바른 번호를 입력해주세요.")

if __name__ == "__main__":
    run_system()