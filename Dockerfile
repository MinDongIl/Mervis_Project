# 1. 가볍고 안정적인 파이썬 3.10 슬림 버전 사용(X)
# 버전 불일치 3.10->3.12
FROM python:3.12-slim

# 2. 컨테이너 내부 작업 경로 설정
WORKDIR /app

# 3. 환경 변수 설정
# - 파이썬 로그가 버퍼링 없이 즉시 출력되도록 설정 (중요)
ENV PYTHONUNBUFFERED=1
# - 타임존을 한국 시간(KST)으로 고정 (주식 매매 필수)
ENV TZ=Asia/Seoul

# 4. 필수 시스템 패키지 설치
# 저사양 서버 안정성을 위해 불필요한 파일은 설치 후 바로 삭제
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tzdata \
    git \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 5. 의존성 파일 복사 및 설치
# requirements.txt가 먼저 복사되어야 캐시를 활용해 빌드 속도가 빨라짐
COPY requirements.txt .
# 메모리 절약을 위해 --no-cache-dir 옵션 필수 사용
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 전체 복사
# .dockerignore에 등록된 파일(venv 등)은 제외하고 복사됨
COPY . .

# 7. 실행 명령 (컨테이너가 켜지면 매니저 자동 실행)
CMD ["python", "mervis_server_manager.py"]