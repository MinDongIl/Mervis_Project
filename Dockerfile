# 1. 베이스 이미지
FROM python:3.12-slim

# 2. 작업 디렉토리
WORKDIR /app

# 3. 환경 변수
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

# 4. 시스템 패키지 설치 (gcc, build-essential 추가)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tzdata \
    git \
    build-essential \
    python3-dev \
    gcc \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 5. 의존성 설치
COPY requirements.txt .
RUN pip install "pip==26.0.1" setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 6. 소스 복사
COPY . .

# 7. 실행 명령
CMD ["python", "mervis_server_manager.py"]