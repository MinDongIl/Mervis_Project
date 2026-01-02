import requests
import secret
import kis_auth
import mervis_state
import time 

# 기준일자(BYMD) 파라미터 대응을 위한 공통 함수 수정
def _fetch_chart(ticker, gubn, bymd=""):
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
            "BYMD": bymd, # 특정 날짜 이후 데이터 조회를 위해 사용
            "MODP": "1", 
            "KEYB": ""
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            data = res.json()
            
            if data.get('rt_cd') == '0' and len(data.get('output2', [])) > 0:
                return data['output2']
                
        except Exception as e:
            continue
    
    return None

def get_daily_chart(ticker, bymd=""):
    return _fetch_chart(ticker, "0", bymd)

def get_weekly_chart(ticker, bymd=""):
    return _fetch_chart(ticker, "1", bymd)

def get_monthly_chart(ticker, bymd=""):
    return _fetch_chart(ticker, "2", bymd)

def get_yearly_chart(ticker, bymd=""):
    # 월봉("2") 데이터를 가져와서 최근 12개월치만 사용
    data = _fetch_chart(ticker, "2", bymd)
    if data:
        # 데이터가 너무 많으면 머비스가 헷갈리므로 최근 12개월(1년)로 제한
        return data[:12] 
    return None