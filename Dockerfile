# 1. 베이스 이미지: Python 3.12 Slim (경량화 버전)
FROM python:3.12-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 환경 변수 설정
# PYTHONUNBUFFERED: 로그 즉시 출력 (모니터링 필수)
# TZ: 서울 시간대 설정
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

# 4. 시스템 패키지 설치 및 정리
# git: 라이브러리 설치 등에 필요할 수 있음
# curl: 상태 확인용 (선택 사항)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tzdata \
    git \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 5. 의존성 설치 (캐시 활용을 위해 먼저 수행)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 복사
# (.dockerignore에 정의된 파일들은 자동으로 제외됨)
COPY . .

# 7. 실행 명령
# 서버 시작 스크립트 실행
CMD ["python", "mervis_server_manager.py"]