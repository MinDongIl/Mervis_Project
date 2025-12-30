import requests
import secret
import kis_auth
import mervis_state
import time 

# 공통 차트 데이터 요청 함수
def _fetch_chart(ticker, gubn):
    # API 호출 전 잠시 대기 (모의투자 서버 부하 방지)
    time.sleep(0.2)
    
    token = kis_auth.get_access_token()
    if not token: 
        print(f"[Chart] Error: No token found.")
        return None
    
    mode = mervis_state.get_mode()
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    path = "uapi/overseas-price/v1/quotations/price"
    url = f"{base_url}/{path}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "HHDFS76240000"
    }

    exchanges = ["NAS", "NYS", "AMS"]
    
    for exc in exchanges:
        params = {
            "AUTH": "", 
            "EXCD": exc, 
            "SYMB": ticker,
            "GUBN": gubn,
            "BYMD": "", 
            "MODP": "1", 
            "KEYB": ""
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            data = res.json()
            
            if data['rt_cd'] != '0':
                # 에러 발생 시 로그 출력 (단, 잦은 에러는 무시 가능)
                # print(f"[API Fail] {ticker}({exc}) GUBN:{gubn} -> {data['msg1']}")
                pass
            
            if data['rt_cd'] == '0' and len(data['output2']) > 0:
                return data['output2']
                
        except Exception as e:
            print(f"[Network Error] {ticker}: {e}")
            continue
    
    # 실패 로그 최소화
    # print(f"[Final Fail] Failed to fetch data for {ticker}. (GUBN: {gubn})")     
    return None

def get_daily_chart(ticker):
    return _fetch_chart(ticker, "0")

def get_weekly_chart(ticker):
    return _fetch_chart(ticker, "1")

def get_monthly_chart(ticker):
    return _fetch_chart(ticker, "2")

def get_yearly_chart(ticker):
    return _fetch_chart(ticker, "2") # 년봉은 월봉 API 파라미터 활용 가능 여부 확인 필요하나 일단 유지