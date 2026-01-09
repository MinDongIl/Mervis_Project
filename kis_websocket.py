import websocket
import json
import time
import threading
import logging
import kis_auth
import mervis_state
import notification

# 미국 주식 실시간 체결가 TR ID
TR_ID_REAL = "HDFSCNT0" 
WS_URL_REAL = "ws://ops.koreainvestment.com:21000"

# 최대 동시 감시 종목 수
MAX_WATCH_LIMIT = 40

# 글로벌 감시자 인스턴스
_active_watcher = None

# 사용자가 직접 지정한 알림 타겟
_user_watch_list = {}

def add_watch_condition(ticker, target_price, condition="GE", tag="지정가"):
    """
    [외부 호출용] 감시 조건 추가
    """
    global _user_watch_list, _active_watcher
    ticker = ticker.upper()
    
    if ticker not in _user_watch_list:
        _user_watch_list[ticker] = []
        
    # 중복 조건 방지
    for item in _user_watch_list[ticker]:
        if item['price'] == float(target_price) and item['cond'] == condition:
            return False

    # 조건 리스트에 추가
    _user_watch_list[ticker].append({
        "price": float(target_price),
        "cond": condition,
        "tag": tag
    })
    
    logging.info(f"[Watch List] Added {ticker} - {tag} ${target_price} ({condition})")
    
    # 실시간 감시자에 구독 추가 요청
    if _active_watcher and _active_watcher.is_running:
        _active_watcher.add_new_target(ticker)
        
    return True

def remove_watch_condition(ticker):
    global _user_watch_list
    ticker = ticker.upper()
    if ticker in _user_watch_list:
        del _user_watch_list[ticker]
        logging.info(f"[Watch List] Removed User Target: {ticker}")
        return True
    return False

class MervisWatcher:
    def __init__(self, target_list):
        self.initial_targets = [item['code'] for item in target_list]
        self.subscribed_tickers = set() 
        self.ws = None
        self.ws_key = None
        self.is_running = False
        self.base_url = WS_URL_REAL 

    def _subscribe_target(self, ticker):
        # KIS 서버에 구독 요청 전송
        if not self.ws or not self.is_running: return
        
        tr_key = f"DNAS{ticker}"
        req_body = {
            "header": {
                "approval_key": self.ws_key,
                "custtype": "P", "tr_type": "1", "content-type": "utf-8"
            },
            "body": { "input": { "tr_id": TR_ID_REAL, "tr_key": tr_key } }
        }
        try:
            self.ws.send(json.dumps(req_body))
            self.subscribed_tickers.add(ticker)
            logging.info(f"[Watcher] Subscribed: {ticker}")
            time.sleep(0.05) 
        except Exception as e:
            logging.error(f"[Watcher] Subscribe Failed ({ticker}): {e}")

    def _unsubscribe_target(self, ticker):
        # KIS 서버에 구독 취소 요청 전송
        if not self.ws or not self.is_running: return
        
        tr_key = f"DNAS{ticker}"
        req_body = {
            "header": {
                "approval_key": self.ws_key,
                "custtype": "P", "tr_type": "2", 
                "content-type": "utf-8"
            },
            "body": { "input": { "tr_id": TR_ID_REAL, "tr_key": tr_key } }
        }
        try:
            self.ws.send(json.dumps(req_body))
            if ticker in self.subscribed_tickers:
                self.subscribed_tickers.remove(ticker)
            logging.info(f"[Watcher] Unsubscribed: {ticker}")
            time.sleep(0.05)
        except Exception as e:
            logging.error(f"[Watcher] Unsubscribe Failed ({ticker}): {e}")

    def manage_subscription_limit(self):
        # 구독 종목 수 한계 초과 시 사용자 지정 외 종목 제거
        if len(self.subscribed_tickers) < MAX_WATCH_LIMIT:
            return

        candidates = [t for t in self.subscribed_tickers if t not in _user_watch_list]
        
        if candidates:
            victim = candidates[0]
            logging.info(f"[Smart Queue] Removing low-priority: {victim}")
            self._unsubscribe_target(victim)
        else:
            logging.warning("[Smart Queue] Watch list full of user-selected items.")

    def add_new_target(self, ticker):
        if ticker in self.subscribed_tickers:
            return 

        self.manage_subscription_limit()
        
        if len(self.subscribed_tickers) < MAX_WATCH_LIMIT:
            self._subscribe_target(ticker)

    def check_user_alert(self, ticker, current_price, change_rate):
        # 체결 시 다중 조건 확인 및 달성된 조건 삭제
        global _user_watch_list
        if ticker not in _user_watch_list: return

        conditions = _user_watch_list[ticker]
        triggered_indexes = [] 

        for i, watch in enumerate(conditions):
            target = watch['price']
            cond = watch['cond']
            tag = watch['tag']
            is_triggered = False
            msg = ""

            if cond == "GE" and current_price >= target: 
                is_triggered = True
                msg = f"[{tag} 달성] {ticker} ${target} 돌파 (현재 ${current_price})"
            elif cond == "LE" and current_price <= target: 
                is_triggered = True
                msg = f"[{tag} 도달] {ticker} ${target} 이하 (현재 ${current_price})"

            if is_triggered:
                logging.info(f"[ALERT] {msg}")
                # 손절은 빨간색, 익절/목표는 파란색
                noti_color = "red" if "손절" in tag else "blue"
                notification.send_alert("매매 신호 감지", msg, color=noti_color)
                triggered_indexes.append(i)

        # 달성된 조건만 역순으로 삭제
        for i in sorted(triggered_indexes, reverse=True):
            del _user_watch_list[ticker][i]

        # 남은 조건이 없으면 종목 키 삭제
        if not _user_watch_list[ticker]:
            del _user_watch_list[ticker]

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
                    if len(raw_data) > 15:
                        raw_ticker = raw_data[0]
                        ticker = raw_ticker[4:] if len(raw_ticker) > 4 else raw_ticker
                        price = float(raw_data[11]) 
                        change_rate = float(raw_data[14])
                        # 거래량 파싱 (미국주식 체결통보 기준 인덱스 확인 필요, 통상 13~15 인근)
                        # KIS 해외주식 체결가 TR: 11=현재가, 14=등락률, 13=체결량(틱), 12=누적거래량
                        volume = float(raw_data[12]) 

                        # 1. State 모듈에 실시간 가격 전송 (동적 캔들용)
                        mervis_state.update_realtime_price(ticker, price, change_rate, volume)
                        
                        # 2. 알림 조건 확인
                        self.check_user_alert(ticker, price, change_rate)
                    
        except Exception as e:
            logging.debug(f"Parsing Error: {e}")

    def on_error(self, ws, error):
        logging.error(f"[Watcher Error] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("[Watcher] Disconnected.")
        self.is_running = False
        self.subscribed_tickers.clear()

    def on_open(self, ws):
        logging.info("[Watcher] Connected.")
        self.is_running = True
        
        count = 0
        for ticker in self.initial_targets:
            if count >= MAX_WATCH_LIMIT: break
            self._subscribe_target(ticker)
            count += 1
            
    def start_loop(self):
        self.ws_key = kis_auth.get_websocket_key()
        if not self.ws_key: return

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

def start_background_monitoring(target_list):
    global _active_watcher
    if _active_watcher and _active_watcher.is_running:
        stop_monitoring()
        time.sleep(1)

    if not target_list: return

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