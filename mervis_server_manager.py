import schedule
import time
import subprocess
import os
import sys
import logging
import signal
import pytz
from datetime import datetime
import notification

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

def run_daily_routine():
    """
    [일일 통합 루틴] 07:00 시작
    순서: 수집(Crawler) -> 채점(Labeler) -> 학습(Trainer) -> 복기(Examiner)
    앞 단계가 성공적으로 끝나야 다음 단계로 넘어갑니다.
    """
    logging.info("========== [일일 루틴] 시작 ==========")
    notification.send_alert("매니저", "일일 루틴(수집/학습/복기)을 시작합니다.")

    # 1단계: 데이터 수집 (Crawler)
    try:
        logging.info(">>> [Step 1] 크롤러 실행 중...")
        # check=True: 에러 발생 시 즉시 예외 발생시켜 중단
        subprocess.run([PYTHON_CMD, "mervis_crawler.py"], check=True)
        logging.info("<<< [Step 1] 수집 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Critical] 크롤링 실패로 루틴 중단: {e}")
        notification.send_alert("매니저[오류]", "크롤링 실패로 일일 작업이 중단되었습니다.", color="red")
        return # 여기서 중단

    # 2단계: 정답지 채점 (Labeler)
    try:
        logging.info(">>> [Step 2] 라벨링(수익률 계산) 실행 중...")
        subprocess.run([PYTHON_CMD, "mervis_labeler.py"], check=True)
        logging.info("<<< [Step 2] 라벨링 완료.")
    except subprocess.CalledProcessError as e:
        logging.error(f"[Error] 라벨링 실패: {e}")
        # 라벨링 실패 시 학습은 의미 없으므로 중단할지, 계속할지 결정. 안전하게 중단 권장.
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
        # 학습 실패해도 복기는 진행하도록 continue (return 안함)

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
            learning_process.terminate() # 안전하게 종료
        logging.info("매니저가 종료되었습니다.")