import requests
import secret
import kis_auth
import mervis_state
from datetime import datetime, time
import pytz
import json

# 시장 개장 여부 확인 함수
def is_market_open():
    try:
        ny_tz = pytz.timezone('US/Eastern')
        ny_now = datetime.now(ny_tz)
        if ny_now.weekday() >= 5: return False
        curr = ny_now.time()
        return time(9, 30) <= curr <= time(16, 0)
    except:
        return False

# 종목 스캔 함수
def get_market_rank(excd, gubun, count=20):
    token = kis_auth.get_access_token()
    if not token: return []

    mode = mervis_state.get_mode()
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    path = "uapi/overseas-stock/v1/quotations/inquire-search"
    url = f"{base_url}/{path}"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "FHKST03030100"
    }
    
    params = {
        "AUTH": "", "EXCD": excd, "GUBN": gubun, "COND": "0",
        "INQR_STRT_CRTI": "", "INQR_END_CRTI": "", "VOL_TNTE": "",
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        
        try:
            data = res.json()
        except json.JSONDecodeError:
            print(f" [Check] JSON decode failed. Response: {res.text[:100]}")
            return []

        targets = []
        if data['rt_cd'] == '0':
            for item in data['output'][:count]:
                price = float(item['last'])
                vol = int(item['vol'])
                if price < 2 or vol == 0: continue
                
                targets.append({
                    "code": item['symb'],
                    "name": item['name'],
                    "price": price,
                    "diff": item['rate'],
                    "market": excd,
                    "reason": gubun
                })
        else:
            print(f" [API Error] {data['msg1']} (Code: {data['rt_cd']})")
            
        return targets

    except Exception as e:
        print(f" [Network Error] {e}")
        return []

# 동적 스캔 및 타겟 확보 함수
def get_dynamic_targets():
    is_open = is_market_open()
    status = "OPEN" if is_open else "CLOSED"
    print(f"[Mervis] Market Status: {status}")
    print(f"[Mervis] Mining trend data...")

    targets = {}
    
    markets = ["NAS", "NYS"]
    # 0:Volume, 1:Rise
    conditions = [("0", "Volume"), ("1", "Rise")]
    
    success_scan = False
    
    for mkt in markets:
        for cond_code, cond_name in conditions:
            raw_list = get_market_rank(mkt, cond_code, 15)
            if raw_list:
                success_scan = True
                print(f" -> [{mkt}] {cond_name}: {len(raw_list)} items found")
                
            for item in raw_list:
                if item['code'] not in targets:
                    item['tag'] = f"{mkt} {cond_name}"
                    targets[item['code']] = item

    final_list = list(targets.values())

    # 스캔 실패 시 기본 유니버스 로드
    if not final_list:
        print("\n[Warning] Live scanning unavailable (Server maintenance or Closed).")
        print("[Action] Loading 'Universe List' for testing.")
        
        universe = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "AMD", "QQQ", "SPY", "SOXL"]
        
        for code in universe:
            final_list.append({"code": code, "name": "Universe", "price": 0})
            
    else:
        print(f"\n[Mervis] Scan complete. Total {len(final_list)} targets acquired.")

    return final_list