import requests
import json
import os
import kis_auth
import mervis_state

def send_order(ticker, price, qty, is_buy=True):
    token = kis_auth.get_access_token()
    if not token: return False

    mode = mervis_state.get_mode()
    
    # 환경 변수 로드
    config = kis_auth.get_env_config(mode)
    base_url = config['base_url']
    app_key = config['app_key']
    app_secret = config['app_secret']

    # 계좌 정보 로드 (환경 변수)
    if mode == "REAL":
        cano = os.getenv("KIS_CANO_REAL", "")
        prdt = os.getenv("KIS_ACNT_PRDT_CD_REAL", "")
        # [안전장치] 실전 모드에서 매매는 사용자 확인 필요 (여기선 일단 로그만 찍음)
        print(f"[주의] 실전 모드({ticker}) 주문은 현재 비활성화 상태입니다.")
        return False
    else:
        cano = os.getenv("KIS_CANO_MOCK", "")
        prdt = os.getenv("KIS_ACNT_PRDT_CD_MOCK", "")
        tr_id = "VTTT1002U" if is_buy else "VTTT1006U"

    path = "uapi/overseas-stock/v1/trading/order"
    url = f"{base_url}/{path}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": prdt,
        "OVRS_EXCG_CD": "NASD",
        "PDNO": ticker,
        "ORD_DVSN": "00",
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": str(price),
        "ORD_SVR_DVSN_CD": "0"
    }

    try:
        res = requests.post(url, headers=headers, data=json.dumps(params), timeout=5)
        data = res.json()
        if data['rt_cd'] == '0':
            print(f"[주문성공] {ticker} {'매수' if is_buy else '매도'} 접수")
            return True
        else:
            print(f"[주문실패] {data['msg1']}")
            return False
    except Exception as e:
        print(f"[오류] {e}")
        return False

def buy_order(ticker, price, qty):
    return send_order(ticker, price, qty, True)

def sell_order(ticker, price, qty):
    return send_order(ticker, price, qty, False)