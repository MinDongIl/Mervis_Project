import os
import sys
import time
import socket
import psutil
from flask import Flask, jsonify, render_template_string, request
from multiprocessing import Process
from datetime import timedelta

app = Flask(__name__)

START_TIME = time.time()
TOTAL_REQUESTS = 0
REQUEST_TIMESTAMPS = []

@app.before_request
def track_requests():
    global TOTAL_REQUESTS, REQUEST_TIMESTAMPS
    if request.path != '/api/status':
        TOTAL_REQUESTS += 1
        current_time = time.time()
        REQUEST_TIMESTAMPS.append(current_time)
        REQUEST_TIMESTAMPS = [ts for ts in REQUEST_TIMESTAMPS if current_time - ts <= 1.0]

HTML_TEMPLATE = """
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

def cpu_stress(duration=30):
    timeout = time.time() + duration
    while time.time() < timeout:
        pass

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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