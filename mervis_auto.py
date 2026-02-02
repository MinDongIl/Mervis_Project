import time
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler

# 기존 모듈 임포트
import mervis_bigquery
import mervis_brain
import mervis_state
import kis_websocket
import notification

# --- 로깅 설정 (학습 로그) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [LEARNING] %(message)s',
    handlers=[
        RotatingFileHandler('mervis_learning.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- 전역 변수 ---
is_running = True

def job_realtime_learning():
    """
    [실시간 학습 루프]
    지속적으로 종목 상태를 체크하고, 분석 결과를 DB에 적재.
    """
    logging.info("실시간 분석 및 학습 프로세스 가동 시작.")
    
    while is_running:
        try:
            # 1. 감시 중인 핵심 40개 종목 리스트 가져오기
            active_tickers = mervis_state.get_all_realtime_tickers()
            
            if active_tickers:
                for ticker in active_tickers:
                    if not is_running: break

                    # 2. 실시간 데이터 스냅샷 (가격, 거래량 등)
                    rt_data = mervis_state.get_realtime_data(ticker)
                    if not rt_data: continue

                    # 3. Brain 분석 실행 (학습)
                    # analyze_stock 함수 내부에서 '전략'이 도출되면 자동으로 BigQuery(trade_history)에 저장
                    item = {"code": ticker, "price": rt_data['price']}
                    result = mervis_brain.analyze_stock(item)
                    
                    if result:
                        report = result.get('report', '')
                        current_p = rt_data['price']
                        
                        # [단타 신호 알림]
                        # 사용자가 직접 매매할 수 있도록 중요 신호(매수/매도 권고)만 선별하여 알림 발송
                        if "매수추천" in report or "매수 권고" in report:
                            logging.info(f"[신호 포착] {ticker} 매수 시그널 발생 (${current_p}) - DB 저장 완료")
                            notification.send_alert(
                                f"[매수 권고] {ticker}", 
                                f"현재가: ${current_p}\n분석 결과가 학습되었습니다.\n\n{report[:200]}...",
                                color='blue'
                            )
                        elif "매도권고" in report:
                            logging.info(f"[신호 포착] {ticker} 매도 시그널 발생 (${current_p}) - DB 저장 완료")
                            notification.send_alert(
                                f"[매도 권고] {ticker}", 
                                f"현재가: ${current_p}\n이익 실현 또는 손절이 필요할 수 있습니다.",
                                color='red'
                            )

            # 사이클 간 대기 (API 호출 제한 및 과부하 방지, 1분 주기)
            time.sleep(60) 

        except Exception as e:
            logging.error(f"학습 루프 중 오류 발생: {e}")
            time.sleep(10)

def main():
    global is_running
    
    logging.info("="*40)
    logging.info(" [MERVIS] 실시간 심층 학습 시스템 시작 (REAL Mode)")
    logging.info("="*40)

    mervis_state.set_mode("REAL") 
    logging.info(f"운용 모드: {mervis_state.get_mode()} (실시간 데이터 학습)")

    # 2. 학습 대상 로드 (빅쿼리에서 선별된 주요 40개 종목)
    try:
        targets = mervis_bigquery.get_tickers_from_db(limit=40)
        if not targets:
            logging.error("DB에서 학습 대상을 찾을 수 없습니다. 종료합니다.")
            return
        
        logging.info(f"학습 대상 로드 완료: {len(targets)}개 우량/급등 종목")
        # 로그 간소화를 위해 종목 나열은 생략하거나 필요 시 주석 해제
        # for t in targets: logging.info(f" - {t['code']}")
            
    except Exception as e:
        logging.error(f"DB 연결 및 대상 로드 실패: {e}")
        return

    # 3. 웹소켓 연결 (실시간 호가 데이터 수신)
    try:
        kis_websocket.start_background_monitoring(targets)
        logging.info("KIS 실시간 웹소켓 연결 성공. 데이터 수신 중...")
    except Exception as e:
        logging.error(f"Websocket 연결 실패: {e}")
        return

    # 4. 학습 스레드 시작
    learning_thread = threading.Thread(target=job_realtime_learning, daemon=True)
    learning_thread.start()

    # 5. 메인 프로세스 유지
    notification.send_alert("학습 시작", f"머비스가 실시간 학습을 시작했습니다.\n대상: {len(targets)}종목")
    
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logging.info("사용자 요청으로 종료합니다.")
    finally:
        is_running = False
        kis_websocket.stop_monitoring()
        logging.info("시스템 안전하게 종료됨.")

if __name__ == "__main__":
    main()