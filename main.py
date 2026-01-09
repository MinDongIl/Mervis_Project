import sys
import time
import datetime
import logging
import threading
import holidays
import pytz 
from logging.handlers import RotatingFileHandler

import kis_scan
import mervis_brain
import mervis_ai
import mervis_state
import mervis_profile
import mervis_bigquery
import update_volume_tier
import kis_websocket 
import kis_account
import notification
import mervis_examiner 

# 전역 변수 및 스레드 상태 관리
is_scheduled = False
scheduled_thread = None

analysis_thread = None
is_analyzing = False

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        logger.handlers = []

    file_handler = RotatingFileHandler('mervis.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def check_market_open_time():
    # 뉴욕 현지 시간 기준 장 시작 여부 판단
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.datetime.now(tz_ny) 
    
    date_ny = now_ny.date()
    us_holidays = holidays.US()
    
    date_str = date_ny.strftime("%Y-%m-%d")
    if date_str in us_holidays:
        return 2, f"휴장일({us_holidays[date_str]})", 0
    
    if now_ny.weekday() >= 5:
        return 2, "주말", 0

    market_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    
    if now_ny < market_open:
        wait_sec = (market_open - now_ny).total_seconds()
        return 1, "개장 전 대기", wait_sec
        
    market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_ny < market_close:
        return 0, "장 운영 중", 0
        
    return 2, "장 마감", 0

def job_realtime_analysis():
    # 백그라운드 실시간 전략 분석 루프
    global is_analyzing
    logging.info("[Analysis Thread] 실시간 전략 분석 스레드 시작")
    
    while is_analyzing:
        try:
            # 현재 감시 중인 종목 리스트 조회
            active_tickers = mervis_state.get_all_realtime_tickers()
            
            if active_tickers:
                for ticker in active_tickers:
                    if not is_analyzing: break

                    # 실시간 데이터 스냅샷 조회
                    rt_data = mervis_state.get_realtime_data(ticker)
                    if not rt_data: continue

                    item = {"code": ticker, "price": rt_data['price']}
                    
                    # Brain 분석 실행
                    result = mervis_brain.analyze_stock(item)
                    
                    report = result.get('report', '')
                    current_p = rt_data['price']
                    
                    if "매수추천" in report or "매수 권고" in report:
                        title = f"[매수 신호] {ticker}"
                        msg = f"현재가: ${current_p}\n{report[:200]}..."
                        notification.send_alert(title, msg, color='blue')
                        logging.info(f"[SIGNAL] {ticker} 매수 신호 발생 (${current_p})")
            
            # 분석 주기 1분
            for _ in range(60): 
                if not is_analyzing: break
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"[Analysis Thread Error] {e}")
            time.sleep(5)

    logging.info("[Analysis Thread] 실시간 전략 분석 스레드 종료")

def start_analysis_thread():
    global analysis_thread, is_analyzing
    if is_analyzing: return
    is_analyzing = True
    analysis_thread = threading.Thread(target=job_realtime_analysis, daemon=True)
    analysis_thread.start()

def stop_analysis_thread():
    global is_analyzing
    is_analyzing = False

def scheduled_market_watcher(targets):
    global is_scheduled
    is_scheduled = True
    
    _, _, wait_sec = check_market_open_time()
    wait_min = int(wait_sec // 60)
    
    logging.info(f"Scheduled monitoring started. Waiting {wait_min} minutes.")
    notification.send_alert("예약 설정됨", f"미 증시 개장까지 {wait_min}분 남았습니다. 대기 모드로 진입합니다.")
    
    while wait_sec > 0:
        if not is_scheduled:
            logging.info("Scheduled monitoring cancelled by user.")
            return
        sleep_time = min(10, wait_sec)
        time.sleep(sleep_time)
        wait_sec -= sleep_time
    
    if is_scheduled:
        notification.send_alert("장 시작", "미 증시 개장. 실시간 감시를 시작합니다.")
        print("\n [System] 예약된 실시간 감시가 시작되었습니다.")
        
        # 감시 및 분석 시작
        kis_websocket.start_background_monitoring(targets)
        start_analysis_thread()
        
        is_scheduled = False

def system_init():
    print("==================================================")
    print(" [MERVIS] 시스템 초기화 중...")
    print("==================================================")
    
    setup_logging()
    logging.info("System Start.")
    notification.send_alert("시스템 부팅", "머비스 시스템이 초기화되었습니다.")

    print(" [Check] 데이터베이스 상태 점검...", end=" ")
    is_fresh = mervis_bigquery.check_db_freshness()
    
    if is_fresh:
        print("최신 상태입니다.")
        logging.info("DB is up-to-date.")
    else:
        print("업데이트 필요.")
        print(" [Process] 거래량 분석 데이터 갱신 중...")
        try:
            update_volume_tier.update_volume_data()
            print(" [Success] DB 업데이트 완료.")
        except Exception as e:
            print(f" [Warning] 업데이트 실패: {e}")
            
    print("==================================================\n")

def run_system():
    global is_scheduled, scheduled_thread
    
    system_init()
    
    # 부팅 시 복기 수행
    try:
        mervis_examiner.run_examination()
    except Exception as e:
        print(f" [System Error] 복기 시스템 실행 중 오류: {e}")

    print(" [모드 선택]")
    print(" 1. 실전 투자 (REAL)")
    print(" 2. 모의 투자 (MOCK)")
    
    choice = input(" >> 선택 (1/2): ").strip()
    mervis_state.set_mode(choice)
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    print(f"\n [System] {mode_name} 모드로 시작합니다.")
    notification.send_alert("모드 설정", f"시스템이 {mode_name} 모드로 설정되었습니다.")

    print(f" [Process] 자산 현황 동기화 중 ({mode_name})...")
    try:
        my_asset = kis_account.get_my_total_assets()
        if my_asset:
            print(f" -> 총 자산: ${my_asset['total']:,.2f}")
            mervis_bigquery.save_daily_balance(
                total_asset=my_asset['total'],
                cash=my_asset['cash'],
                stock_val=my_asset['stock'],
                pnl_daily=my_asset['pnl']
            )
            notification.send_alert("자산 현황", f"총 자산: ${my_asset['total']:,.2f}\n수익률: {my_asset['pnl']}%")
    except Exception as e:
        print(f" -> [Error] 자산 동기화 오류: {e}")

    while True:
        ws_active = kis_websocket.is_active()
        
        if ws_active:
            status_text = "가동 중 (ON)"
            if is_analyzing: status_text += " + Brain 분석 중"
        elif is_scheduled:
            status_text = "개장 대기 중 (Reserved)"
        else:
            status_text = "중지됨 (OFF)"

        print(f"\n==================================================")
        print(f" [메인 메뉴] 실시간 감시: {status_text}")
        print(f"==================================================")
        print(" 1. 전체 시장 자동 스캔 (Auto Scan)")
        print(" 2. 특정 종목 검색 (Sniper Search)")
        print(" 3. 대화 모드 (Free Talk)")
        print(" 4. 시스템 종료 (Exit)")
        
        if ws_active:
            print(" 5. 실시간 감시 중단")
        elif is_scheduled:
            print(" 5. 예약 취소 (대기 중단)")
        else:
            print(" 5. 실시간 감시 시작 (백그라운드)")
        
        menu = input(" >> 입력: ").strip()
        
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
                    if res: results.append(res)
                print("\n [완료] 분석 완료. 상담 모드로 진입합니다.")
                
                if results:
                    report_text = f"[{mode_name} 스캔 리포트]\n"
                    for r in results: report_text += f"[{r['code']}] {r['report']}\n"
                    mervis_ai.start_consulting(report_text)
            except KeyboardInterrupt:
                print("\n [중단] 취소되었습니다.")

        elif menu == '2':
            code = input(" >> 종목 티커 입력: ").upper().strip()
            if code:
                print(f" [Mervis] '{code}' 정밀 분석 중...")
                target_item = {"code": code, "name": "Manual", "price": 0}
                res = mervis_brain.analyze_stock(target_item)
                if res:
                    print(" -> 분석 완료.")
                    mervis_ai.start_consulting(f"[Sniper Report]\n{res['report']}")
                else:
                    print(" -> 분석 실패.")

        elif menu == '3':
            print(" [Mervis] 대화 모드입니다. (종료: 'q')")
            context = f"[System Info] Mode: {mode_name}, Monitor: {status_text}"
            mervis_ai.start_consulting(context)

        elif menu == '4':
            if kis_websocket.is_active(): kis_websocket.stop_monitoring()
            stop_analysis_thread()
            is_scheduled = False
            print(" [시스템] 종료합니다.")
            sys.exit(0)

        elif menu == '5':
            if ws_active:
                print(" [Process] 실시간 감시를 중단합니다...")
                kis_websocket.stop_monitoring()
                stop_analysis_thread()
                notification.send_alert("감시 중단", "실시간 감시가 중단되었습니다.", color="red")
            
            elif is_scheduled:
                print(" [Process] 개장 대기 예약을 취소합니다.")
                is_scheduled = False
                notification.send_alert("예약 취소", "실시간 감시 예약이 취소되었습니다.")
            
            else:
                targets = mervis_bigquery.get_tickers_from_db(limit=40)
                if not targets:
                    print(" [오류] 감시 대상 종목이 없습니다.")
                    continue

                status, msg, wait_sec = check_market_open_time()
                
                if status == 2: 
                    print(f" [경고] {msg}입니다.")
                    c = input(" >> 그래도 강제로 켜시겠습니까? (y/n): ")
                    if c.lower() == 'y':
                        kis_websocket.start_background_monitoring(targets)
                        start_analysis_thread()
                        print(" [알림] 강제 실행되었습니다.")
                
                elif status == 1: 
                    print(f" [알림] 현재 장 시작 전입니다. ({int(wait_sec//60)}분 남음)")
                    print(" [Process] 뉴욕 시간 09:30(개장)에 맞춰 예약을 설정합니다.")
                    scheduled_thread = threading.Thread(target=scheduled_market_watcher, args=(targets,), daemon=True)
                    scheduled_thread.start()
                    
                else: 
                    print(" [Process] 장 운영 시간입니다. 즉시 감시를 시작합니다.")
                    kis_websocket.start_background_monitoring(targets)
                    start_analysis_thread()
                    
                    notification.send_alert("감시 시작", f"실시간 감시를 시작합니다. 대상: {len(targets)}개")

        else:
            print(" [경고] 올바른 번호가 아닙니다.")

if __name__ == "__main__":
    run_system()