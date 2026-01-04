import requests
import json
import logging
import mervis_state
import kis_auth
import secret

def _get_api_config():
    mode = mervis_state.get_mode()
    
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
        cano = getattr(secret, 'CANO_REAL', getattr(secret, 'CANO', ''))
        prdt = getattr(secret, 'ACNT_PRDT_CD_REAL', getattr(secret, 'ACNT_PRDT_CD', ''))
        tr_id_balance = "CTRP6504R"
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK
        cano = getattr(secret, 'CANO_MOCK', '')
        prdt = getattr(secret, 'ACNT_PRDT_CD_MOCK', '')
        tr_id_balance = "VTRP6504R"

    if isinstance(cano, str): cano = cano.strip()
    if isinstance(prdt, str): prdt = prdt.strip()

    return {
        "base_url": base_url,
        "app_key": app_key,
        "app_secret": app_secret,
        "cano": cano,
        "prdt": prdt,
        "tr_id_balance": tr_id_balance
    }

def get_my_total_assets():
    """
    [롤백 버전]
    복잡한 총자산 계산 제외.
    오직 '미국 달러(USD)' 예수금만 찾아서 반환.
    """
    config = _get_api_config()
    token = kis_auth.get_access_token()
    
    if not token:
        logging.error("[Account] Token generation failed.")
        return None

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": config['app_key'],
        "appsecret": config['app_secret'],
        "tr_id": config['tr_id_balance'],
        "custtype": "P"
    }

    # 파라미터는 동일
    params = {
        "CANO": config['cano'],
        "ACNT_PRDT_CD": config['prdt'],
        "WCRC_FRCR_DVSN_CD": "01",
        "NATN_CD": "840",
        "TR_MKET_CD": "00",
        "INQR_DVSN_CD": "00",
        "CTX_AREA_FK": "",
        "CTX_AREA_NK": ""
    }

    path = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    url = f"{config['base_url']}{path}"

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()

        if data['rt_cd'] != '0':
            msg = data.get('msg1', 'Unknown Error')
            print(f" -> [Account Error] {msg}")
            return None
        
        # output2: 외화예수금 상세 리스트
        currencies = data.get('output2', [])
        
        usd_deposit = 0.0
        
        # 리스트를 순회하며 USD 찾기
        if isinstance(currencies, list):
            for currency in currencies:
                if currency.get('crcy_cd') == 'USD':
                    # frcr_dncl_amt_2: 외화예수금
                    usd_deposit = float(currency.get('frcr_dncl_amt_2', 0))
                    break
        
        # [DEBUG] 확인용 출력
        # print("\n" + "="*50)
        # print(f" [DEBUG] USD 잔고 확인: {usd_deposit} $")
        # print("="*50 + "\n")

        return {
            "total": usd_deposit,
            "cash": usd_deposit, 
            "stock": 0.0,
            "pnl": 0.0,
            "currency": "USD" # 통화 단위 USD로 명시
        }

    except Exception as e:
        logging.error(f"[Account System Error] {e}")
        return None

def get_stock_qty(ticker):
    # (기존 로직 유지 - 필요시 구현)
    return 0

if __name__ == "__main__":
    asset = get_my_total_assets()
    if asset:
        print(f"Asset Info: {asset}")