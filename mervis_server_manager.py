import schedule
import time
import subprocess
import os
import sys
import logging
import signal
import pytz
import holidays
from datetime import datetime

# --- 설정 ---
PYTHON_CMD = sys.executable 

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [MANAGER] %(message)s',
    handlers=[
        logging.FileHandler('server_manager.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# 학습 프로세스 관리 변수
learning_process = None

def get_kst_time():
    return datetime.now(pytz.timezone('Asia/Seoul')).strftime("%H:%M:%S")

def is_market_open_day():
    # 뉴욕 기준 주말 및 휴장일 체크
    try:
        tz_ny = pytz.timezone('America/New_York')
        now_ny = datetime.now(tz_ny)
        date_ny = now_ny.date()
        
        # 1. 주말 체크 (토=5, 일=6)
        if now_ny.weekday() >= 5:
            logging.info(f"[Schedule] Today is Weekend (NY: {now_ny.strftime('%A')}).")
            return False

        # 2. 휴장일 체크
        us_holidays = holidays.US(years=date_ny.year)
        if date_ny in us_holidays:
            logging.info(f"[Schedule] Today is Holiday ({us_holidays[date_ny]}).")
            return False
            
        return True
    except Exception as e:
        logging.error(f"[Check Error] {e}")
        return False

def run_daily_routine():
    # [일일 통합 루틴] 07:00 시작 (수집 -> 채점 -> 학습 -> 복기)
    
    # 전일(NY 기준)이 휴장일이면 데이터가 없으므로 건너뜀
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.now(tz_ny)
    
    # 간단 체크: 현재(새벽)가 주말/휴일 범위에 포함되면 스킵
    if now_ny.weekday() >= 5 or now_ny.date() in holidays.US(years=now_ny.year):
        logging.info("[Schedule] Holiday/Weekend detected. Skipping daily routine.")
        return

    logging.info("========== [Daily Routine] Start ==========")
    import notification
    notification.send_alert("매니저", "일일 루틴(수집/학습/복기)을 시작합니다.")

    # 1. 수집
    try:
        logging.info(">>> [Step 1] Crawler Start")
        subprocess.run([PYTHON_CMD, "mervis_crawler.py"], check=True)
    except subprocess.CalledProcessError:
        logging.error("[Critical] Crawler Failed.")
        notification.send_alert("매니저[오류]", "크롤링 실패로 중단됨.", color="red")
        return 

    # 2. 채점
    try:
        logging.info(">>> [Step 2] Labeler Start")
        subprocess.run([PYTHON_CMD, "mervis_labeler.py"], check=True)
    except subprocess.CalledProcessError:
        logging.error("[Error] Labeler Failed.")
        return

    # 3. 학습
    try:
        logging.info(">>> [Step 3] Trainer Start")
        subprocess.run([PYTHON_CMD, "mervis_trainer.py"], check=True)
    except subprocess.CalledProcessError:
        logging.error("[Error] Trainer Failed.")

    # 4. 복기
    try:
        logging.info(">>> [Step 4] Examiner Start")
        subprocess.run([PYTHON_CMD, "mervis_examiner.py"], check=True)
    except subprocess.CalledProcessError:
        logging.error("[Error] Examiner Failed.")

    logging.info("========== [Daily Routine] Finished ==========")
    notification.send_alert("매니저", "일일 작업 완료. 대기 모드 전환.")

def start_learning_mode():
    # [23:30] 실시간 학습 시작
    global learning_process
    
    if not is_market_open_day():
        logging.info("[Schedule] Market Closed. Skip Learning.")
        return

    if learning_process and learning_process.poll() is None:
        return

    logging.info(">>> [Schedule] Market Open. Starting Auto-Learning.")
    import notification
    notification.send_alert("매니저", "미장 개장. 실시간 학습 프로세스 가동.")
    
    try:
        learning_process = subprocess.Popen([PYTHON_CMD, "mervis_auto.py"])
    except Exception as e:
        logging.error(f"Process Start Failed: {e}")

def stop_learning_mode():
    # [06:00] 학습 종료
    global learning_process
    
    if learning_process and learning_process.poll() is None:
        logging.info(">>> [Schedule] Market Close. Stopping process...")
        learning_process.send_signal(signal.SIGINT)
        try:
            learning_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            learning_process.kill()
            
        logging.info("<<< Process Stopped.")
        learning_process = None
        import notification
        notification.send_alert("매니저", "장 마감. 학습 프로세스 종료.")

# 스케줄 설정
schedule.every().day.at("07:00").do(run_daily_routine)
schedule.every().day.at("23:30").do(start_learning_mode)
schedule.every().day.at("06:00").do(stop_learning_mode)

if __name__ == "__main__":
    logging.info("Mervis Server Manager Started.")
    import notification
    notification.send_alert("매니저", "서버 매니저 가동 시작")
    
    while True:
        schedule.run_pending()
        time.sleep(1)