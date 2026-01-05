import sys
import time
import datetime
import logging
import threading
import holidays
import pytz  # [추가] 서머타임 자동 계산을 위한 라이브러리
from logging.handlers import RotatingFileHandler

# 사용자 모듈
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

# [설정] 전역 변수
is_scheduled = False
scheduled_thread = None

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

def check_market_open_time():
    """
    뉴욕 현지 시간을 기준으로 장 시작 여부를 판단 (서머타임 자동 적용)
    Return: (status_code, message, seconds_to_wait)
    """
    # 1. 타임존 설정
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.datetime.now(tz_ny) # 현재 뉴욕 시간
    
    # 2. 휴장/주말 체크
    # holidays 라이브러리는 날짜 객체(date)를 요구함
    date_ny = now_ny.date()
    us_holidays = holidays.US()
    
    date_str = date_ny.strftime("%Y-%m-%d")
    if date_str in us_holidays:
        return 2, f"휴장일({us_holidays[date_str]})", 0
    
    # weekday(): 0(월) ~ 6(일) -> 뉴욕 기준 토(5), 일(6) 체크
    if now_ny.weekday() >= 5:
        return 2, "주말", 0

    # 3. 개장 시간 설정 (뉴욕 기준 09:30)
    market_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    
    # 4. 시간 비교
    # 현재 뉴욕 시간이 06:00 이전(새벽)이라면 -> 장 마감 후 or 장전 (여기선 장전으로 처리)
    # 현재 뉴욕 시간이 16:00 이후라면 -> 장 마감
    
    # [단순화 로직]
    # 현재가 09:30 이전이면 -> 대기
    # 현재가 09:30 ~ 16:00 사이면 -> 장 운영 중
    # (새벽 4시 등 프리마켓 시간대도 일단은 '대기'로 퉁치고 09:30에 정식 가동)

    if now_ny < market_open:
        wait_sec = (market_open - now_ny).total_seconds()
        return 1, "개장 전 대기", wait_sec
        
    # 만약 현재 시간이 09:30은 지났는데, 16:00(장마감)은 안 지났다면
    market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_ny < market_close:
        return 0, "장 운영 중", 0
        
    # 16:00 이후라면 (장 마감)
    return 2, "장 마감", 0

def scheduled_market_watcher(targets):
    """
    백그라운드 예약 대기 (서머타임 고려됨)
    """
    global is_scheduled
    is_scheduled = True
    
    _, _, wait_sec = check_market_open_time()
    wait_min = int(wait_sec // 60)
    
    logging.info(f"Scheduled monitoring started. Waiting {wait_min} minutes.")
    notification.send_alert("예약 설정됨", f"미 증시 개장(NY 09:30)까지 {wait_min}분 남았습니다. 대기 모드로 진입합니다.")
    
    while wait_sec > 0:
        if not is_scheduled:
            logging.info("Scheduled monitoring cancelled by user.")
            return
        # 10초 단위 체크
        sleep_time = min(10, wait_sec)
        time.sleep(sleep_time)
        wait_sec -= sleep_time
    
    if is_scheduled:
        notification.send_alert("장 시작", "🔔 미 증시가 개장했습니다! 실시간 감시를 시작합니다.")
        print("\n [System] 예약된 실시간 감시가 시작되었습니다!")
        kis_websocket.start_background_monitoring(targets)
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

    print(" [모드 선택]")
    print(" 1. 실전 투자 (REAL)")
    print(" 2. 모의 투자 (MOCK)")
    
    choice = input(" >> 선택 (1/2): ").strip()
    mervis_state.set_mode(choice)
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    print(f"\n [System] {mode_name} 모드로 시작합니다.")
    notification.send_alert("모드 설정", f"시스템이 **{mode_name}** 모드로 설정되었습니다.")

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
            is_scheduled = False
            print(" [시스템] 종료합니다.")
            sys.exit(0)

        elif menu == '5':
            if ws_active:
                print(" [Process] 실시간 감시를 중단합니다...")
                kis_websocket.stop_monitoring()
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
                
                if status == 2: # 휴장/주말/마감
                    print(f" [경고] {msg}입니다.")
                    c = input(" >> 그래도 강제로 켜시겠습니까? (y/n): ")
                    if c.lower() == 'y':
                        kis_websocket.start_background_monitoring(targets)
                        print(" [알림] 강제 실행되었습니다.")
                
                elif status == 1: # 장전 대기
                    print(f" [알림] 현재 장 시작 전입니다. ({int(wait_sec//60)}분 남음)")
                    print(" [Process] 뉴욕 시간 09:30(개장)에 맞춰 예약을 설정합니다.")
                    scheduled_thread = threading.Thread(target=scheduled_market_watcher, args=(targets,), daemon=True)
                    scheduled_thread.start()
                    
                else: # 장중 (즉시 실행)
                    print(" [Process] 장 운영 시간입니다. 즉시 감시를 시작합니다.")
                    kis_websocket.start_background_monitoring(targets)
                    notification.send_alert("감시 시작", f"실시간 감시를 시작합니다. 대상: {len(targets)}개")

        else:
            print(" [경고] 올바른 번호가 아닙니다.")

if __name__ == "__main__":
    run_system()