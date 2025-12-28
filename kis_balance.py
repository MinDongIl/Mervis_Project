import requests
import secret
import kis_auth
import mervis_state

def get_stock_info(ticker):
    token = kis_auth.get_access_token()
    if not token: return 0, 0
    
    mode = mervis_state.get_mode()
    if mode == "REAL":
        # 실전 잔고 조회 로직 (키 변경)
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
        cano = secret.CANO_REAL
        prdt = secret.ACNT_PRDT_CD_REAL
        tr_id = "VTTS3012R" # *주의: 실전 TR코드는 다를 수 있음 (TTTS3012R 등)
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK
        cano = secret.CANO_MOCK
        prdt = secret.ACNT_PRDT_CD_MOCK
        tr_id = "VTTS3012R"

    path = "uapi/overseas-stock/v1/trading/inquire-balance"
    url = f"{base_url}/{path}"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": tr_id
    }
    
    params = {
        "CANO": cano, "ACNT_PRDT_CD": prdt,
        "OVRS_EXCG_CD": "NASD", "TR_CRC": "USD",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()
        if data['rt_cd'] == '0':
            for item in data['output1']:
                if item['ovrs_pdno'] == ticker:
                    return int(item['ovrs_cblc_qty']), float(item['frcr_pchs_amt1'])
        return 0, 0
    except:
        return 0, 0