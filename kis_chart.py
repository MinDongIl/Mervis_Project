import requests
import secret
import kis_auth
import mervis_state

def get_daily_price(ticker):
    token = kis_auth.get_access_token()
    if not token: return None
    
    mode = mervis_state.get_mode()
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    path = "uapi/overseas-price/v1/quotations/dailyprice"
    url = f"{base_url}/{path}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "HHDFS76240000"
    }

    params = {
        "AUTH": "", "EXCD": "NAS", "SYMB": ticker,
        "GUBN": "0", "BYMD": "", "MODP": "0"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()
        if data['rt_cd'] == '0':
            return data['output2']
        return []
    except Exception:
        return []