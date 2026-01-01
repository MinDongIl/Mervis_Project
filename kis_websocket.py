import websocket
import json
import time
import threading
import secret
import kis_auth
import mervis_state

# [설정] 미국 주식 실시간 체결가 TR ID
TR_ID_REAL = "HDFSCNT0" 

# 웹소켓 URL (KIS 가이드 기준)
WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
WS_URL_MOCK = "ws://openapivts.koreainvestment.com:21000"

class MervisWatcher:
    def __init__(self, target_list):
        self.target_list = target_list # 감시할 종목 리스트 [{'code': 'AAPL', 'tag': '...'}, ...]
        self.ws = None
        self.ws_key = None
        self.stop_signal = False
        
        # 현재 모드에 따른 URL 설정
        self.mode = mervis_state.get_mode()
        self.base_url = WS_URL_REAL if self.mode == "REAL" else WS_URL_MOCK
        
        print(f"[Watcher] Initializing WebSocket ({self.mode} Mode)...")

    def on_message(self, ws, message):
        # KIS 웹소켓 데이터는 텍스트 형태가 많음
        # 데이터 포맷: 0(암호화여부)|TR_ID|데이터개수|데이터본문(aaaa^bbbb^...)
        
        try:
            # 첫 메시지(PINGPONG 등) 처리
            if message[0] == '{':
                data = json.loads(message)
                if 'header' in data and data['header'].get('tr_id') == 'PINGPONG':
                    ws.send(message) # Pong 응답
                    return

            parts = message.split('|')
            if len(parts) > 3:
                tr_id = parts[1]
                
                if tr_id == TR_ID_REAL:
                    # 데이터 본문 파싱 (구분자: ^)
                    # [주의] 인덱스는 API 버전에 따라 다를 수 있으나 보통:
                    # 0:종목코드, 1:체결시간, 2:체결가, 11:체결량 등
                    raw_data = parts[3].split('^')
                    
                    ticker = raw_data[0]
                    price = float(raw_data[2])
                    vol = raw_data[11]
                    change_rate = raw_data[4] # 등락률
                    
                    # [로그] 너무 빠르면 정신없으므로, 특정 조건(예: 급변)일 때만 찍거나
                    # 지금은 테스트를 위해 모든 체결 데이터 출력
                    print(f" [Live] {ticker} : ${price} ({change_rate}%) | Vol: {vol}")
                    
                    # === [매수/매도 로직 연결 포인트] ===
                    # self.brain.check_price_action(ticker, price)
                    
        except Exception as e:
            # 데이터 파싱 에러는 빈번할 수 있으므로 치명적이지 않으면 무시
            pass

    def on_error(self, ws, error):
        print(f"[Watcher Error] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("[Watcher] Connection Closed.")

    def on_open(self, ws):
        print("[Watcher] Connected! Subscribing to targets...")
        
        for item in self.target_list:
            ticker = item['code']
            
            # [중요] 구독 키(tr_key) 생성
            # 미국 주식은 "D + 시장구분(NAS/NYS/AMS) + 종목코드" 형식을 씀
            # DB/Scan에서 시장 정보를 안 가져왔다면, 임시로 주요 거래소 시도
            # (KIS API는 종목코드만 보내도 되는 경우가 있으나, 정석은 시장구분 포함)
            
            # 여기서는 편의상 DB에 시장정보가 없으므로 'DNAS'(나스닥)를 기본으로 붙이거나
            # yfinance 등으로 시장을 확인해야 함. 
            # 일단 'DNAS' 접두어 사용 (대부분의 기술주가 나스닥이므로)
            # 추후 DB에 'market' 컬럼 추가 권장.
            tr_key = f"DNAS{ticker}" 

            req_body = {
                "header": {
                    "approval_key": self.ws_key,
                    "custtype": "P",
                    "tr_type": "1", # 1: 등록, 2: 해제
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
            
        print(f"[Watcher] Monitoring started for {len(self.target_list)} stocks.")

    def start(self):
        # 1. 웹소켓 키 발급 (kis_auth V14.0 사용)
        self.ws_key = kis_auth.get_websocket_key()
        if not self.ws_key:
            print("[Watcher] Approval Key Missing. Aborting.")
            return

        # 2. 연결 시작
        self.ws = websocket.WebSocketApp(
            f"{self.base_url}/tryitout/{TR_ID_REAL}",
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        self.ws.run_forever()

# 외부 호출용 함수
def run_monitoring(target_list):
    if not target_list:
        print("[Watcher] Target list is empty.")
        return

    watcher = MervisWatcher(target_list)
    try:
        watcher.start()
    except KeyboardInterrupt:
        print("[Watcher] Stopped by user.")