import websocket
import json
import time
import threading
import logging
import kis_auth
import mervis_state
import notification

# [설정] 미국 주식 실시간 체결가 TR ID
TR_ID_REAL = "HDFSCNT0" 
WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
WS_URL_MOCK = "ws://ops.koreainvestment.com:21000"

# 글로벌 감시자 인스턴스
_active_watcher = None

# [신규] 사용자가 지정한 알림 타겟 관리 (메모리 저장)
# 구조: { "TSLA": {"target_price": 300.0, "condition": "GE"} }  # GE: Greater or Equal
_user_watch_list = {}

def add_watch_condition(ticker, target_price, condition="GE"):
    """
    사용자가 대화 중에 요청한 감시 조건을 등록하는 함수
    ticker: 종목코드
    target_price: 목표가
    condition: 'GE'(이상), 'LE'(이하)
    """
    global _user_watch_list
    ticker = ticker.upper()
    _user_watch_list[ticker] = {
        "target_price": float(target_price),
        "condition": condition
    }
    logging.info(f"[Watch List] Added {ticker} (Target: {target_price}, Cond: {condition})")
    return True

def remove_watch_condition(ticker):
    global _user_watch_list
    ticker = ticker.upper()
    if ticker in _user_watch_list:
        del _user_watch_list[ticker]
        logging.info(f"[Watch List] Removed {ticker}")
        return True
    return False

class MervisWatcher:
    def __init__(self, target_list):
        self.target_list = target_list
        self.ws = None
        self.ws_key = None
        self.is_running = False
        
        self.mode = mervis_state.get_mode()
        self.base_url = WS_URL_REAL 
        
    def check_user_alert(self, ticker, current_price, change_rate):
        """
        [User Custom Alert]
        사용자가 '직접 부탁한' 조건에 도달했는지 확인하고 알림 전송
        """
        global _user_watch_list
        
        # 1. 사용자가 등록한 종목인지 확인
        if ticker not in _user_watch_list:
            return

        watch_info = _user_watch_list[ticker]
        target = watch_info['target_price']
        cond = watch_info['condition']
        
        is_triggered = False
        msg = ""

        # 2. 조건 비교
        if cond == "GE" and current_price >= target: # 목표가 이상 도달 (익절/돌파)
            is_triggered = True
            msg = f"[목표 도달] {ticker} 목표가 ${target} 돌파! (현재 ${current_price})"
        
        elif cond == "LE" and current_price <= target: # 목표가 이하 도달 (손절/저점매수)
            is_triggered = True
            msg = f"[가격 도달] {ticker} 지정가 ${target} 도달! (현재 ${current_price})"

        # 3. 알림 전송 및 목록에서 제거(일회성 알림인 경우)
        if is_triggered:
            logging.info(f"[ALERT TRIGGERED] {msg}")
            notification.send_alert("매매 신호 감지", msg, color="blue")
            
            # 알림 후 목록에서 삭제 (중복 알림 방지, 필요시 유지 가능)
            del _user_watch_list[ticker] 

    def on_message(self, ws, message):
        try:
            # 1. 핑퐁 처리
            if message[0] == '{':
                data = json.loads(message)
                if 'header' in data and data['header'].get('tr_id') == 'PINGPONG':
                    ws.send(message)
                    return

            # 2. 데이터 파싱
            parts = message.split('|')
            if len(parts) > 3:
                tr_id = parts[1]
                
                if tr_id == TR_ID_REAL:
                    raw_data = parts[3].split('^')
                    
                    if len(raw_data) > 15:
                        raw_ticker = raw_data[0]
                        ticker = raw_ticker[4:] if len(raw_ticker) > 4 else raw_ticker
                        
                        price = float(raw_data[11]) # 현재가
                        change_rate = float(raw_data[14]) # 등락률
                        
                        # [Log] 기본 로그는 파일에 계속 남김 (데이터 수집용)
                        logging.info(f"[Live] {ticker}: ${price} ({change_rate}%)")
                        
                        # [Alert] 사용자가 부탁한 조건만 체크 (무조건적인 급등락 알림 삭제됨)
                        self.check_user_alert(ticker, price, change_rate)
                    
        except Exception as e:
            logging.debug(f"Parsing Error: {e}")

    def on_error(self, ws, error):
        logging.error(f"[Watcher Error] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("[Watcher] Disconnected.")
        self.is_running = False

    def on_open(self, ws):
        logging.info("[Watcher] Connected! Monitoring started.")
        self.is_running = True
        
        # 기본 감시 대상 구독 (Top 40 등)
        for item in self.target_list:
            ticker = item['code']
            tr_key = f"DNAS{ticker}" 
            
            req_body = {
                "header": {
                    "approval_key": self.ws_key,
                    "custtype": "P", "tr_type": "1", "content-type": "utf-8"
                },
                "body": { "input": { "tr_id": TR_ID_REAL, "tr_key": tr_key } }
            }
            ws.send(json.dumps(req_body))
            time.sleep(0.05) 

    def start_loop(self):
        self.ws_key = kis_auth.get_websocket_key()
        if not self.ws_key:
            logging.error("[Watcher] Failed to get WebSocket Key.")
            return

        ws_url = f"{self.base_url}"
        
        self.ws = websocket.WebSocketApp(
            ws_url,
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
    
    if _active_watcher and _active_watcher.is_running:
        stop_monitoring()
        time.sleep(1)

    if not target_list:
        logging.warning("[Watcher] Target list is empty.")
        return

    _active_watcher = MervisWatcher(target_list)
    t = threading.Thread(target=_active_watcher.start_loop)
    t.daemon = True 
    t.start()

def stop_monitoring():
    global _active_watcher
    if _active_watcher:
        _active_watcher.stop()
        _active_watcher = None
        logging.info("[Watcher] Monitoring Stopped.")

def is_active():
    global _active_watcher
    return _active_watcher is not None and _active_watcher.is_running