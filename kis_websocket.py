import websocket
import json
import time
import threading
import kis_auth
import mervis_state

# [설정] 미국 주식 실시간 체결가 TR ID
TR_ID_REAL = "HDFSCNT0" 
WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
WS_URL_MOCK = "ws://openapivts.koreainvestment.com:21000"

# 글로벌 감시자 인스턴스 (메인에서 제어용)
_active_watcher = None

class MervisWatcher:
    def __init__(self, target_list):
        self.target_list = target_list
        self.ws = None
        self.ws_key = None
        self.is_running = False
        
        self.mode = mervis_state.get_mode()
        self.base_url = WS_URL_REAL if self.mode == "REAL" else WS_URL_MOCK
        
        # 이전 가격 저장용 (급등락 감지)
        self.prev_prices = {} 

    def check_signal(self, ticker, price, change_rate):
        """
        [Alert System] 실시간 가격 변동에 따른 매수/매도 알림
        - 현재는 단순 급등락(-3% ~ +3%) 예시
        - 추후 Brain의 목표가(Target Price)와 연동 가능
        """
        try:
            c_rate = float(change_rate)
            
            # [Trigger 1] 급등 알림 (3% 이상)
            if c_rate >= 3.0:
                 print(f"\n 🔥 [ALERT] {ticker} 급등 감지! 현재가 ${price} (+{c_rate}%)")
            
            # [Trigger 2] 급락 알림 (-3% 이하)
            elif c_rate <= -3.0:
                 print(f"\n 💧 [ALERT] {ticker} 급락 주의! 현재가 ${price} ({c_rate}%)")
                 
        except: pass

    def on_message(self, ws, message):
        try:
            if message[0] == '{':
                data = json.loads(message)
                if 'header' in data and data['header'].get('tr_id') == 'PINGPONG':
                    ws.send(message)
                    return

            parts = message.split('|')
            if len(parts) > 3:
                tr_id = parts[1]
                if tr_id == TR_ID_REAL:
                    raw_data = parts[3].split('^')
                    ticker = raw_data[0]
                    price = float(raw_data[2])
                    vol = raw_data[11]
                    change_rate = raw_data[4]
                    
                    # [Log] 실시간 로그 출력 (백그라운드에서도 보임)
                    # 너무 빠르면 시끄러우니 간소화된 로그 사용
                    print(f" [Live] {ticker}: ${price} ({change_rate}%)", end='\r')
                    
                    # [Signal] 알림 체크
                    self.check_signal(ticker, price, change_rate)
                    
        except: pass

    def on_error(self, ws, error):
        print(f" [Watcher Error] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("\n [Watcher] Disconnected.")
        self.is_running = False

    def on_open(self, ws):
        print("\n [Watcher] Connected! Monitoring started in Background.")
        self.is_running = True
        
        for item in self.target_list:
            ticker = item['code']
            tr_key = f"DNAS{ticker}" # 임시: 나스닥 가정
            
            req_body = {
                "header": {"approval_key": self.ws_key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
                "body": {"input": {"tr_id": TR_ID_REAL, "tr_key": tr_key}}
            }
            ws.send(json.dumps(req_body))
            time.sleep(0.05)

    def start_loop(self):
        self.ws_key = kis_auth.get_websocket_key()
        if not self.ws_key:
            print("[Watcher] Key Error.")
            return

        self.ws = websocket.WebSocketApp(
            f"{self.base_url}/tryitout/{TR_ID_REAL}",
            on_open=self.on_open, on_message=self.on_message,
            on_error=self.on_error, on_close=self.on_close
        )
        self.ws.run_forever()

    def stop(self):
        if self.ws:
            self.ws.close()
        self.is_running = False

# [외부 제어 함수]
def start_background_monitoring(target_list):
    global _active_watcher
    
    # 이미 실행 중이면 중단 후 재시작
    if _active_watcher and _active_watcher.is_running:
        stop_monitoring()
        time.sleep(1)

    if not target_list:
        print(" [Watcher] 타겟 리스트가 비어있습니다.")
        return

    _active_watcher = MervisWatcher(target_list)
    
    # 스레드로 실행 (Non-blocking)
    t = threading.Thread(target=_active_watcher.start_loop)
    t.daemon = True # 메인 프로그램 종료 시 같이 종료
    t.start()

def stop_monitoring():
    global _active_watcher
    if _active_watcher:
        _active_watcher.stop()
        _active_watcher = None
        print(" [Watcher] 감시 종료.")

def is_active():
    global _active_watcher
    return _active_watcher is not None and _active_watcher.is_running