import os
import sys
import time
import socket
import psutil
import uuid
import redis
from flask import Flask, jsonify, render_template_string, request, make_response
from multiprocessing import Process
from datetime import timedelta

app = Flask(__name__)

# 1. 글로벌 변수 및 Redis 설정
START_TIME = time.time()
TOTAL_REQUESTS = 0
REQUEST_TIMESTAMPS = []

# 대기열 댐(Queue) 크기: 서버 1대가 안정적으로 감당할 최대 유저 수
MAX_ACTIVE_USERS = 500  

# Redis 연결 (Terraform에서 주입한 REDIS_HOST 환경변수 사용)
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)
    # 연결 테스트
    redis_client.ping()
    print(f"Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"Redis connection failed: {e}")
    redis_client = None

# 2. HTML 템플릿 정의

# SRE 대시보드 화면 (통과한 유저에게만 보임)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Mervis SRE Dashboard</title>
    <style>
        body { font-family: 'Consolas', monospace; background-color: #1e1e1e; color: #00ff00; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #2d2d2d; padding: 20px; border-radius: 10px; box-shadow: 0 0 15px rgba(0,255,0,0.2); }
        h1 { text-align: center; border-bottom: 1px solid #444; padding-bottom: 10px; }
        .status-box { margin: 20px 0; padding: 15px; border: 1px solid #555; border-radius: 5px; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .metric-card { background: #333; padding: 15px; border-radius: 5px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #00ffff; margin-top: 10px; }
        .bar-container { background: #444; height: 25px; border-radius: 5px; overflow: hidden; margin-top: 5px; }
        .bar { height: 100%; text-align: center; line-height: 25px; color: black; font-weight: bold; transition: width 0.5s ease-in-out; }
        .btn-group { display: flex; justify-content: space-around; margin-top: 30px; }
        button { background: #333; color: white; border: 1px solid #555; padding: 10px 20px; cursor: pointer; font-size: 16px; border-radius: 5px; }
        button:hover { background: #555; }
        .btn-danger { color: #ff4d4d; border-color: #ff4d4d; }
        .btn-danger:hover { background: #ff4d4d; color: black; }
        .btn-warning { color: #ffcc00; border-color: #ffcc00; }
        .btn-warning:hover { background: #ffcc00; color: black; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Mervis Infrastructure Status</h1>
        
        <div class="status-box">
            <h3>Connected Server (Hostname)</h3>
            <h2 id="hostname" style="color: #00ffff;">Loading...</h2>
        </div>

        <div class="grid-container">
            <div class="metric-card">
                <div>Uptime</div>
                <div id="uptime" class="metric-value">00:00:00</div>
            </div>
            <div class="metric-card">
                <div>Client IP</div>
                <div id="client-ip" class="metric-value">-</div>
            </div>
            <div class="metric-card">
                <div>Total Requests</div>
                <div id="total-requests" class="metric-value">0</div>
            </div>
            <div class="metric-card">
                <div>Current RPS</div>
                <div id="rps" class="metric-value">0</div>
            </div>
        </div>

        <div class="status-box">
            <h3>CPU Usage</h3>
            <div class="bar-container">
                <div id="cpu-bar" class="bar" style="width: 0%; background: #00ff00;">0%</div>
            </div>
        </div>

        <div class="status-box">
            <h3>Memory Usage</h3>
            <div class="bar-container">
                <div id="mem-bar" class="bar" style="width: 0%; background: #00ff00;">0%</div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn-warning" onclick="triggerStress()">Trigger CPU Load</button>
            <button class="btn-danger" onclick="triggerCrash()">Crash Server</button>
        </div>
    </div>

    <script>
        setInterval(() => {
            fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('hostname').innerText = data.hostname;
                    document.getElementById('uptime').innerText = data.uptime;
                    document.getElementById('client-ip').innerText = data.client_ip;
                    document.getElementById('total-requests').innerText = data.total_requests;
                    document.getElementById('rps').innerText = data.rps;
                    
                    const cpuBar = document.getElementById('cpu-bar');
                    cpuBar.style.width = data.cpu + '%';
                    cpuBar.innerText = data.cpu + '%';
                    cpuBar.style.background = data.cpu > 80 ? '#ff4d4d' : '#00ff00';

                    const memBar = document.getElementById('mem-bar');
                    memBar.style.width = data.memory + '%';
                    memBar.innerText = data.memory + '%';
                    memBar.style.background = data.memory > 80 ? '#ff4d4d' : '#00ff00';
                }).catch(err => {
                    document.getElementById('hostname').innerText = "SERVER DOWN";
                    document.getElementById('hostname').style.color = "#ff4d4d";
                });
        }, 1000);

        function triggerStress() {
            fetch('/api/stress');
            alert('CPU Load test started. (Duration: 30 seconds)');
        }

        function triggerCrash() {
            if(confirm('Execute Server Crash?')) {
                fetch('/api/crash');
            }
        }
    </script>
</body>
</html>
"""

# 수용량 초과 시 보여줄 대기열 화면
WAITING_ROOM_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Mervis 서비스 접속 대기중</title>
    <style>
        body { font-family: 'Arial', sans-serif; text-align: center; padding: 50px; background-color: #f8f9fa; color: #333; }
        .box { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: inline-block; max-width: 500px; }
        h2 { color: #0056b3; }
        .rank { font-size: 36px; font-weight: bold; color: #e83e8c; margin: 20px 0; }
        .warning { color: red; font-weight: bold; font-size: 14px; margin-top: 30px; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 2s linear infinite; margin: 0 auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="box">
        <h2>잠시만 기다려주세요.</h2>
        <p>현재 접속자가 많아 서비스 보호를 위해 대기열을 발급합니다.</p>
        <div class="spinner"></div>
        <div class="rank" id="rankDisplay">대기 순서 확인 중...</div>
        <p>순서가 되면 자동으로 페이지가 이동됩니다.</p>
        <p class="warning">※ 새로고침(F5)을 누르시면 대기 순서가 맨 뒤로 밀려납니다. 이 화면을 유지해주세요.</p>
    </div>

    <script>
        function checkStatus() {
            fetch('/api/wait_status')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'allowed') {
                        // 차례가 되어 메인 대시보드로 통과!
                        window.location.reload(); 
                    } else if (data.status === 'waiting') {
                        // 현재 대기 순서 업데이트
                        document.getElementById('rankDisplay').innerText = "내 앞 대기자: " + data.rank + " 명";
                    }
                }).catch(err => console.log(err));
        }
        // 3초마다 내 순서가 줄어들었는지 서버에 물어봄(Polling)
        setInterval(checkStatus, 3000);
        checkStatus();
    </script>
</body>
</html>
"""

# 3. 요청 카운터 미들웨어
@app.before_request
def track_requests():
    global TOTAL_REQUESTS, REQUEST_TIMESTAMPS
    # 상태 확인 API들은 카운트에서 제외
    if request.path not in ['/api/status', '/api/wait_status', '/health']:
        TOTAL_REQUESTS += 1
        current_time = time.time()
        REQUEST_TIMESTAMPS.append(current_time)
        REQUEST_TIMESTAMPS = [ts for ts in REQUEST_TIMESTAMPS if current_time - ts <= 1.0]

# 4. 라우팅 로직 (대기열 댐 포함)
@app.route('/')
def index():
    # Redis가 죽었거나 연결 안 되면 기존처럼 무조건 통과 (장애 방지)
    if not redis_client:
        return render_template_string(DASHBOARD_HTML)

    # 1. 유저 식별용 쿠키 확인
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())

    try:
        # 2. 이미 통과하여 정상 이용 중인 유저인지 확인
        if redis_client.sismember('active_users', user_id):
            resp = make_response(render_template_string(DASHBOARD_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp

        # 3. 현재 서버의 전체 수용량 확인 (현재 통과된 유저 수)
        active_count = redis_client.scard('active_users')
        
        if active_count < MAX_ACTIVE_USERS:
            # 수용 공간이 남았을 경우: 통과 처리
            redis_client.sadd('active_users', user_id)
            resp = make_response(render_template_string(DASHBOARD_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp
        else:
            # 수용 공간 초과: 대기열(ZSET)에 Timestamp 기준으로 줄 세우기
            if not redis_client.zscore('waitlist', user_id):
                redis_client.zadd('waitlist', {user_id: time.time()})
            
            # 대기열 화면(WAITING_ROOM_HTML) 반환
            resp = make_response(render_template_string(WAITING_ROOM_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp
            
    except redis.RedisError as e:
        print(f"Redis error in index: {e}")
        # Redis 에러 시 앱이 터지지 않고 통과시키도록 Fallback
        return render_template_string(DASHBOARD_HTML)


@app.route('/api/wait_status')
def wait_status():
    """대기열 화면에서 3초마다 순서를 확인하는 API"""
    if not redis_client:
        return jsonify({"status": "allowed"})

    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"status": "error"}), 400
    
    try:
        # 혹시 자리가 나서 통과 처리 되었는지 확인
        if redis_client.sismember('active_users', user_id):
            return jsonify({"status": "allowed"})
        
        # 내 대기열 순위 확인
        rank = redis_client.zrank('waitlist', user_id)
        if rank is not None:
            active_count = redis_client.scard('active_users')
            
            # 빈 자리가 생겼고, 내 순위가 그 빈 자리 개수 안에 들어간다면 통과
            if active_count < MAX_ACTIVE_USERS and rank < (MAX_ACTIVE_USERS - active_count):
                redis_client.zrem('waitlist', user_id)
                redis_client.sadd('active_users', user_id)
                return jsonify({"status": "allowed"})
                
            # 아직 내 차례가 아니면 현재 대기 순서 반환
            return jsonify({"status": "waiting", "rank": rank + 1})
            
        return jsonify({"status": "error", "message": "Not in waitlist"}), 400
        
    except redis.RedisError:
        return jsonify({"status": "allowed"})


# 5. 기존 SRE 인프라 진단 및 제어 로직
def cpu_stress(duration=30):
    timeout = time.time() + duration
    while time.time() < timeout:
        pass

@app.route('/api/status')
def status():
    uptime_seconds = int(time.time() - START_TIME)
    uptime_str = str(timedelta(seconds=uptime_seconds))

    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    current_time = time.time()
    current_rps = len([ts for ts in REQUEST_TIMESTAMPS if current_time - ts <= 1.0])

    return jsonify({
        'hostname': socket.gethostname(),
        'cpu': psutil.cpu_percent(interval=0.1),
        'memory': psutil.virtual_memory().percent,
        'uptime': uptime_str,
        'total_requests': TOTAL_REQUESTS,
        'rps': current_rps,
        'client_ip': client_ip or "Unknown"
    })

@app.route('/health')
def health():
    return "OK", 200

@app.route('/api/crash')
def crash():
    os._exit(1)

@app.route('/api/stress')
def stress():
    cores = psutil.cpu_count(logical=True)
    for _ in range(cores):
        p = Process(target=cpu_stress, args=(30,))
        p.start()
    return jsonify({"message": "Stress test started"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)