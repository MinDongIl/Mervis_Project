import threading
from datetime import datetime

# [머비스 상태 관리자]
# 모드 설정 및 실시간 데이터 공유 메모리 역할

# --- 설정 관리 ---
CURRENT_MODE = "REAL" 

def set_mode(mode_input):
    global CURRENT_MODE
    if mode_input in ["1", "real", "REAL"]:
        CURRENT_MODE = "REAL"
    else:
        CURRENT_MODE = "MOCK"

def get_mode():
    return CURRENT_MODE

def is_real():
    return CURRENT_MODE == "REAL"

# --- 실시간 데이터 메모리 (In-Memory DB) ---

# 구조: { "TSLA": {"price": 250.0, "change": 1.5, "volume": 10000, "updated_at": ...} }
_REALTIME_STORE = {}
_DATA_LOCK = threading.Lock() # 스레드 충돌 방지용

def update_realtime_price(ticker, price, change_rate, volume):
    # 웹소켓에서 수신한 최신 데이터 갱신
    with _DATA_LOCK:
        _REALTIME_STORE[ticker] = {
            "price": float(price),
            "change": float(change_rate),
            "volume": float(volume),
            "updated_at": datetime.now()
        }

def get_realtime_data(ticker):
    # 전략 모듈에서 최신 데이터 조회용
    with _DATA_LOCK:
        data = _REALTIME_STORE.get(ticker)
        if data:
            return data.copy() # 원본 훼손 방지
        return None

def get_all_realtime_tickers():
    # 현재 메모리에 올라와 있는 모든 종목 코드 반환
    with _DATA_LOCK:
        return list(_REALTIME_STORE.keys())