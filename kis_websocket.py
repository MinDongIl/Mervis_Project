import websocket
import json
import time
import threading
import logging
import kis_auth
import mervis_state

# [설정] 미국 주식 실시간 체결가 TR ID
TR_ID_REAL = "HDFSCNT0" 
WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
WS_URL_MOCK = "ws://openapivts.koreainvestment.com:21000"

# 글로벌 감시자 인스턴스
_active_watcher = None

class MervisWatcher:
    def __init__(self, target_list):
        self.target_list = target_list
        self.ws = None
        self.ws_key = None
        self.is_running = False
        
        self.mode = mervis_state.get_mode()
        self.base_url = WS_URL_REAL if self.mode == "REAL" else WS_URL_MOCK
        
        # 이전 가격 저장용
        self.prev_prices = {} 

    def check_signal(self, ticker, price, change_rate):
        """
        [Alert System] 급등락 감지 (로그 파일에만 기록)
        """
        try:
            c_rate = float(change_rate)
            
            # [안전장치] 데이터 오류로 날짜(20260102 등)가 퍼센트로 들어오면 무시
            if abs(c_rate) > 500: 
                return

            # [Trigger 1] 급등 알림 (5% 이상)
            if c_rate >= 5.0:
                logging.warning(f"[ALERT] {ticker} Surge detected: ${price} (+{c_rate}%)")
            
            # [Trigger 2] 급락 알림 (-5% 이하)
            elif c_rate <= -5.0:
                logging.warning(f"[ALERT] {ticker} Plunge detected: ${price} ({c_rate}%)")
                 
        except: 
            pass

    def on_message(self, ws, message):
        try:
            # 1. 핑퐁 처리 (연결 유지)
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
                    # 데이터 본문 분리
                    raw_data = parts[3].split('^')
                    
                    # [데이터 매핑 수정]
                    # Index 0: RSYM (종목코드)
                    # Index 2: PRIC (현재가)
                    # Index 5: RATE (등락률) *기존 4번(DIFF)에서 5번으로 수정
                    
                    if len(raw_data) > 10:
                        ticker = raw_data[0]
                        price = float(raw_data[2])
                        change_rate = float(raw_data[5]) # 여기가 날짜가 아니라 진짜 수익률
                        
                        # [Log] 파일에만 기록 (콘솔 출력 X)
                        logging.info(f"[Live] {ticker}: ${price} ({change_rate}%)")
                        
                        # [Signal] 알림 체크
                        self.check_signal(ticker, price, change_rate)
                    
        except Exception as e:
            # 파싱 에러 등은 디버그 로그로 처리
            logging.debug(f"Parsing Error: {e}")

    def on_error(self, ws, error):
        logging.error(f"[Watcher Error] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("[Watcher] Disconnected.")
        self.is_running = False

    def on_open(self, ws):
        logging.info("[Watcher] Connected! Background monitoring started.")
        self.is_running = True
        
        # 구독 신청
        for item in self.target_list:
            ticker = item['code']
            # 실시간 체결가 Key 형식: DNAS + Ticker
            tr_key = f"DNAS{ticker}" 
            
            req_body = {
                "header": {
                    "approval_key": self.ws_key,
                    "custtype": "P",
                    "tr_type": "1",
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": TR_ID_REAL,
                        "tr_key": tr_key
                    }
                }
            }
            ws.send(json.dumps(req_body))
            time.sleep(0.05) # 요청 간격 조절

    def start_loop(self):
        self.ws_key = kis_auth.get_websocket_key()
        if not self.ws_key:
            logging.error("[Watcher] Failed to get WebSocket Key.")
            return

        # 웹소켓 실행
        self.ws = websocket.WebSocketApp(
            f"{self.base_url}/tryitout/{TR_ID_REAL}",
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
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
    
    # 스레드 실행 (데몬 스레드: 메인 종료 시 자동 종료)
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