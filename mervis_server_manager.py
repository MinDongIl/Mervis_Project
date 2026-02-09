import schedule
import time
import subprocess
import os
import sys
import logging
import signal
import pytz
import holidays
from datetime import datetime, time as dtime

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

# 미국 시장 개장 여부 및 휴장일 체크 (main.py 로직 이식)
def is_market_open_day():
    try:
        # 뉴욕 시간 기준 확인
        tz_ny = pytz.timezone('America/New_York')
        now_ny = datetime.now(tz_ny)
        date_ny = now_ny.date()
        
        # 1. 주말 체크 (토=5, 일=6)
        if now_ny.weekday() >= 5:
            logging.info(f"[일정] 오늘은 주말입니다. (NY: {now_ny.strftime('%A')})")
            return False

        # 2. 미국 휴장일 체크
        us_holidays = holidays.US(years=date_ny.year)
        if date_ny in us_holidays:
            holiday_name = us_holidays[date_ny]
            logging.info(f"[일정] 오늘은 미국 휴장일({holiday_name})입니다.")
            return False
            
        return True
    except Exception as e:
        logging.error(f"[Check Error] 날짜 확인 중 오류: {e}")
        # 오류 발생 시 안전하게 False 반환하여 사고 방지
        return False

def run_daily_routine():
    """
    [일일 통합 루틴] 07:00 시작
    순서: 수집(Crawler) -> 채점(Labeler) -> 학습(Trainer) -> 복기(Examiner)
    """
    # 주말/휴일 체크 (어제가 평일이었어야 수집할 데이터가 있음)
    # 07:00 실행 시점은 한국시간 기준 당일이지만, 데이터는 '전날 미장' 데이터임.
    # 따라서 '어제'가 휴장일이었는지 체크하는 것이 정확하나, 
    # 간단하게는 오늘이 화~토요일이고 어제가 휴일이 아니어야 함.
    # 여기서는 안전하게 is_market_open_day()를 호출하되, 
    # 토요일 아침(금요일 장 마감 후)에는 실행되어야 하므로 로직 보정이 필요함.
    
    # KST 07:00 = NY 17:00 (전날 장 마감 후)
    # 즉, NY 기준으로 '어제'가 평일/비휴일이어야 함.
    
    tz_ny = pytz.timezone('America/New_York')
    now_ny = datetime.now(tz_ny)
    # 현재 NY 시간은 전날 오후 5시경이므로, date()는 '장 마감일'을 가리킴.
    
    if now_ny.weekday() >= 5: # 토, 일 (NY 기준)
        logging.info("[Schedule] NY 기준 주말이므로 일일 루틴(데이터 수집)을 건너뜁니다.")
        return

    us_holidays = holidays.US(years=now_ny.year)
    if now_ny.date() in us_holidays:
        logging.info(f"[Schedule] NY 기준 휴장일({us_holidays[now_ny.date()]})이므로 건너뜁니다.")
        return

    logging.info("========== [일일 루틴] 시작 ==========")
    notification.send_alert("매니저", "일일 루틴(수집/학습/복기)을 시작합니다.")

    # 1단계: 데이터 수집 (Crawler)
    try:
        logging.info(">>> [Step 1] 크롤러 실행 중...")
        subprocess.run([PYTHON_CMD, "mervis_crawler.py"], check=True)
        logging.info("<<< [Step 1] 수집 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Critical] 크롤링 실패로 루틴 중단: {e}")
        notification.send_alert("매니저[오류]", "크롤링 실패로 일일 작업이 중단되었습니다.", color="red")
        return 

    # 2단계: 정답지 채점 (Labeler)
    try:
        logging.info(">>> [Step 2] 라벨링(수익률 계산) 실행 중...")
        subprocess.run([PYTHON_CMD, "mervis_labeler.py"], check=True)
        logging.info("<<< [Step 2] 라벨링 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Error] 라벨링 실패: {e}")
        notification.send_alert("매니저[오류]", "라벨링 실패. 학습 단계 건너뜀.", color="red")
        return

    # 3단계: AI 모델 재학습 (Trainer)
    try:
        logging.info(">>> [Step 3] AI 모델 재학습 실행 중...")
        subprocess.run([PYTHON_CMD, "mervis_trainer.py"], check=True)
        logging.info("<<< [Step 3] 학습 및 모델 배포 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Error] 모델 학습 실패: {e}")
        notification.send_alert("매니저[오류]", "모델 학습 실패.", color="red")

    # 4단계: 복기 및 오답노트 (Examiner)
    try:
        logging.info(">>> [Step 4] 매매 복기 실행 중...")
        subprocess.run([PYTHON_CMD, "mervis_examiner.py"], check=True)
        logging.info("<<< [Step 4] 복기 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Error] 복기 실행 실패: {e}")

    logging.info("========== [일일 루틴] 전체 완료 ==========")
    notification.send_alert("매니저", "모든 일일 작업이 완료되었습니다. 서버는 대기 상태로 전환됩니다.")


def start_learning_mode():
    """
    [23:30] 미 증시 개장 - 실시간 학습 모드 시작
    """
    global learning_process
    
    # 휴장일 체크
    if not is_market_open_day():
        logging.info("[Schedule] 오늘은 휴장일입니다. 실시간 학습을 실행하지 않습니다.")
        return

    if learning_process and learning_process.poll() is None:
        logging.warning("이미 학습 프로세스가 실행 중입니다.")
        return

    logging.info(">>> [일정] 미 증시 개장. 실시간 학습(Auto) 프로세스를 시작합니다.")
    notification.send_alert("매니저", "미 증시 개장! 실시간 학습을 시작합니다.")
    
    try:
        # mervis_auto.py를 별도 프로세스로 실행 (백그라운드)
        learning_process = subprocess.Popen([PYTHON_CMD, "mervis_auto.py"])
        logging.info(f"학습 프로세스 실행됨 (PID: {learning_process.pid})")
    except Exception as e:
        logging.error(f"프로세스 시작 실패: {e}")
        notification.send_alert("매니저[오류]", "학습 프로세스 시작 실패", color="red")

def stop_learning_mode():
    """
    [06:00] 미 증시 폐장 - 학습 프로세스 종료
    """
    global learning_process
    
    # 실행 중인 프로세스가 있을 때만 종료 시도
    if learning_process and learning_process.poll() is None:
        logging.info(">>> [일정] 미 증시 폐장. 학습 프로세스를 정리합니다...")
        
        # 정상 종료 요청 (SIGINT)
        learning_process.send_signal(signal.SIGINT)
        
        try:
            learning_process.wait(timeout=10) # 10초 대기
        except subprocess.TimeoutExpired:
            logging.warning("프로세스가 응답하지 않아 강제로 종료합니다.")
            learning_process.kill() # 응답 없을 시 강제 종료
            
        logging.info("<<< [완료] 학습 프로세스가 안전하게 종료되었습니다.")
        learning_process = None
        notification.send_alert("매니저", "장이 마감되어 학습을 종료합니다.")
    else:
        logging.info("현재 실행 중인 학습 프로세스가 없습니다.")

# --- 스케줄 등록 (한국 시간 기준) ---

# 1. 아침 7시: 일일 통합 루틴 시작 (순차 실행)
schedule.every().day.at("07:00").do(run_daily_routine)

# 2. 밤 11시 30분: 장 시작 (실시간 학습 가동)
schedule.every().day.at("23:30").do(start_learning_mode)

# 3. 새벽 6시 00분: 장 마감 (학습 종료)
schedule.every().day.at("06:00").do(stop_learning_mode)

if __name__ == "__main__":
    logging.info("Mervis Server Manager 가동 시작.")
    notification.send_alert("매니저", "서버 매니저가 시작되었습니다.\n스케줄링 대기 중...")
    
    logging.info(f"현재 서버 시간: {datetime.now()}")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("매니저 종료 요청을 받았습니다. 실행 중인 프로세스를 정리합니다.")
        if learning_process:
            learning_process.terminate() 
        logging.info("매니저가 종료되었습니다.")