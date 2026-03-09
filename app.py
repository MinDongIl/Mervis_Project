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

START_TIME = time.time()
TOTAL_REQUESTS = 0
REQUEST_TIMESTAMPS = []

MAX_ACTIVE_USERS = 500  

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
try:
    pool = redis.ConnectionPool(host=REDIS_HOST, port=6379, db=0, decode_responses=True, max_connections=1000)
    redis_client = redis.Redis(connection_pool=pool)
    redis_client.ping()
    print(f"Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"Redis connection failed: {e}")
    redis_client = None


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
        .btn-group { display: flex; justify-content: space-around; margin-top: 30px; flex-wrap: wrap; gap: 10px; }
        button { background: #333; color: white; border: 1px solid #555; padding: 10px 20px; cursor: pointer; font-size: 16px; border-radius: 5px; font-family: 'Consolas', monospace; }
        button:hover { background: #555; }
        .btn-danger { color: #ff4d4d; border-color: #ff4d4d; }
        .btn-warning { color: #ffcc00; border-color: #ffcc00; }
        .btn-primary { color: #00aaff; border-color: #00aaff; font-weight: bold; }
        .btn-purple { color: #d63384; border-color: #d63384; font-weight: bold; }
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

        <div class="btn-group">
            <button class="btn-warning" onclick="triggerStress()">Trigger CPU Load</button>
            <button class="btn-danger" onclick="triggerCrash()">Crash Server</button>
            <button class="btn-primary" onclick="exitService()">Complete & Exit (방 빼기)</button>
            <button class="btn-purple" onclick="resetQueue()">Reset Redis Queue</button>
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
                }).catch(err => {
                    document.getElementById('hostname').innerText = "SERVER DOWN";
                    document.getElementById('hostname').style.color = "#ff4d4d";
                });
        }, 1000);

        function triggerStress() { fetch('/api/stress'); alert('CPU Load started.'); }
        function triggerCrash() { if(confirm('Crash Server?')) fetch('/api/crash'); }
        function exitService() {
            if(confirm('예매를 완료하고 퇴장하시겠습니까?')) window.location.href = '/api/exit';
        }
        function resetQueue() {
            if(confirm('대기열을 0으로 강제 초기화 하시겠습니까? (SRE 테스트용)')) {
                fetch('/api/reset').then(() => alert('초기화 완료!'));
            }
        }
    </script>
</body>
</html>
"""


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
        <p class="warning">※ 새로고침(F5)을 눌러도 대기 순서는 유지됩니다.</p>
    </div>

    <script>
        function checkStatus() {
            fetch('/api/wait_status')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'allowed') {
                        window.location.reload(); 
                    } else if (data.status === 'waiting') {
                        document.getElementById('rankDisplay').innerText = "내 앞 대기자: " + data.rank + " 명";
                    }
                }).catch(err => console.log(err));
        }
        setInterval(checkStatus, 3000);
        checkStatus();
    </script>
</body>
</html>
"""

@app.before_request
def track_requests():
    global TOTAL_REQUESTS, REQUEST_TIMESTAMPS
    if request.path not in ['/api/status', '/api/wait_status', '/health', '/api/exit', '/api/reset']:
        TOTAL_REQUESTS += 1
        current_time = time.time()
        REQUEST_TIMESTAMPS.append(current_time)
        REQUEST_TIMESTAMPS = [ts for ts in REQUEST_TIMESTAMPS if current_time - ts <= 1.0]


def cleanup_zombies(current_time):
    if not redis_client:
        return
    zombies = redis_client.zrangebyscore('last_active', '-inf', current_time - 30)
    if zombies:
        redis_client.zrem('active_users', *zombies)
        redis_client.zrem('waitlist', *zombies)
        redis_client.zrem('last_active', *zombies)

@app.route('/')
def index():
    if not redis_client:
        return make_response("<h1>현재 접속자가 많아 서버를 일시적으로 보호 중입니다. 잠시 후 다시 접속해주세요. (Redis Offline)</h1>", 503)

    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())

    try:
        current_time = time.time()
        cleanup_zombies(current_time)
        
        # 접속 생존 신고
        redis_client.zadd('last_active', {user_id: current_time})

        # 이미 활성화된 유저
        if redis_client.zscore('active_users', user_id) is not None:
            resp = make_response(render_template_string(DASHBOARD_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp

        # 대기열에 이미 있는 유저 (새로고침 시 새치기 차단)
        if redis_client.zscore('waitlist', user_id) is not None:
            resp = make_response(render_template_string(WAITING_ROOM_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp

        active_count = redis_client.zcard('active_users')
        waitlist_count = redis_client.zcard('waitlist')
        
        # 빈자리가 있고, 내 앞에 대기자가 아무도 없을 때만 바로 통과
        if active_count < MAX_ACTIVE_USERS and waitlist_count == 0:
            redis_client.zadd('active_users', {user_id: current_time})
            resp = make_response(render_template_string(DASHBOARD_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp
        else:
            # 대기열에 진입 (순위 점수는 최초 진입 시간 고정)
            redis_client.zadd('waitlist', {user_id: current_time})
            resp = make_response(render_template_string(WAITING_ROOM_HTML))
            resp.set_cookie('user_id', user_id, max_age=3600)
            return resp
            
    except redis.RedisError as e:
        print(f"Redis error: {e}")
        return make_response("<h1>현재 접속자가 많아 서버를 일시적으로 보호 중입니다. 잠시 후 다시 접속해주세요.</h1>", 503)

@app.route('/api/wait_status')
def wait_status():
    if not redis_client:
        return jsonify({"status": "allowed"})

    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"status": "error"}), 400
    
    try:
        current_time = time.time()
        cleanup_zombies(current_time)
        redis_client.zadd('last_active', {user_id: current_time})

        if redis_client.zscore('active_users', user_id) is not None:
            return jsonify({"status": "allowed"})
        
        rank = redis_client.zrank('waitlist', user_id)
        if rank is not None:
            active_count = redis_client.zcard('active_users')
            
            if active_count < MAX_ACTIVE_USERS and rank < (MAX_ACTIVE_USERS - active_count):
                redis_client.zrem('waitlist', user_id)
                redis_client.zadd('active_users', {user_id: current_time})
                return jsonify({"status": "allowed"})
                
            return jsonify({"status": "waiting", "rank": rank + 1})
            
        return jsonify({"status": "error", "message": "Not in waitlist or expired"}), 400
        
    except redis.RedisError:
        return jsonify({"status": "allowed"})

@app.route('/api/exit')
def exit_service():
    user_id = request.cookies.get('user_id')
    if user_id and redis_client:
        try:
            redis_client.zrem('active_users', user_id)
            redis_client.zrem('waitlist', user_id)
            redis_client.zrem('last_active', user_id)
        except redis.RedisError:
            pass

    resp = make_response("""
        <div style="text-align:center; margin-top:100px; font-family:sans-serif;">
            <h1 style="color:#00aaff;">예매가 완료되어 퇴장 처리되었습니다.</h1>
            <a href="/" style="font-size:20px; text-decoration:none; color:#333; border:1px solid #ccc; padding:10px 20px; border-radius:5px;">메인으로 다시 접속해보기</a>
        </div>
    """)
    resp.set_cookie('user_id', '', expires=0)
    return resp

@app.route('/api/reset')
def reset_redis():
    if redis_client:
        redis_client.flushdb()
        return jsonify({"message": "Redis Queue Cleared!"}), 200
    return jsonify({"error": "Redis not connected"}), 500


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

    user_id = request.cookies.get('user_id')
    if user_id and redis_client:
        try:
            redis_client.zadd('last_active', {user_id: current_time})
        except: pass

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
def health(): return "OK", 200

@app.route('/api/crash')
def crash(): os._exit(1)

@app.route('/api/stress')
def stress():
    cores = psutil.cpu_count(logical=True)
    for _ in range(cores):
        Process(target=cpu_stress, args=(30,)).start()
    return jsonify({"message": "Stress test started"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)