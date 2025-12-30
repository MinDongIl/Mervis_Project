import requests
import secret
import kis_auth
import mervis_state

# [내부 함수] 공통 차트 데이터 요청 (모드 및 토큰 로직 유지)
def _fetch_chart(ticker, gubn):
    token = kis_auth.get_access_token()
    if not token: return None
    
    # [기존 로직 유지] 모의/실전 모드에 따른 키 및 URL 분기 처리
    mode = mervis_state.get_mode()
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    # 기간별 시세 조회(HHDFS76240000) 표준 경로
    path = "uapi/overseas-price/v1/quotations/price"
    url = f"{base_url}/{path}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "HHDFS76240000"
    }

    # 거래소 순회 (NAS -> NYS -> AMS)
    exchanges = ["NAS", "NYS", "AMS"]
    
    for exc in exchanges:
        params = {
            "AUTH": "", 
            "EXCD": exc, 
            "SYMB": ticker,
            "GUBN": gubn, # 0:일, 1:주, 2:월
            "BYMD": "", 
            "MODP": "1",  # 수정주가 반영
            "KEYB": ""
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            data = res.json()
            if data['rt_cd'] == '0' and len(data['output2']) > 0:
                return data['output2']
        except Exception:
            continue
            
    return None

# === [공개 함수] 기간별 데이터 조회 ===

def get_daily_chart(ticker):
    # 일봉 (Day)
    return _fetch_chart(ticker, "0")

def get_weekly_chart(ticker):
    # 주봉 (Week)
    return _fetch_chart(ticker, "1")

def get_monthly_chart(ticker):
    # 월봉 (Month)
    return _fetch_chart(ticker, "2")

def get_yearly_chart(ticker):
    # 년 단위 추세 (월봉 데이터 공유)
    return _fetch_chart(ticker, "2")

# 기존 코드와의 호환성 유지
def get_daily_price(ticker):
    return get_daily_chart(ticker)