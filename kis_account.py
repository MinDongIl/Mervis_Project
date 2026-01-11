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
        tr_id_balance = "CTRP6504R" # 해외주식 잔고 (실전)
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK
        cano = getattr(secret, 'CANO_MOCK', '')
        prdt = getattr(secret, 'ACNT_PRDT_CD_MOCK', '')
        tr_id_balance = "VTRP6504R" # 해외주식 잔고 (모의)

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
    USD 예수금 + 보유 주식 평가액 합산 및 상세 리스트 반환
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

    params = {
        "CANO": config['cano'],
        "ACNT_PRDT_CD": config['prdt'],
        "WCRC_FRCR_DVSN_CD": "01", # 01: 외화, 02: 원화 환산
        "NATN_CD": "840",         # 840: 미국
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

        if data.get('rt_cd') != '0':
            msg = data.get('msg1', 'Unknown Error')
            print(f" -> [Account Error] {msg}")
            return None
        
        # 1. 외화 예수금 (USD) 찾기 (output2)
        currencies = data.get('output2', [])
        usd_deposit = 0.0
        
        if isinstance(currencies, list):
            for cur in currencies:
                # crcy_cd: 통화코드 (USD)
                if cur.get('crcy_cd') == 'USD':
                    usd_deposit = float(cur.get('frcr_dncl_amt_2', 0)) # 외화예수금
                    break
        
        # 2. 보유 주식 상세 파싱 (output1)
        holdings = data.get('output1', [])
        stock_val_total = 0.0
        total_pnl_amt = 0.0
        
        holding_list = []

        if isinstance(holdings, list):
            for stock in holdings:
                # ovrs_pdno: 해외상품번호(티커), ovrs_cblc_qty: 해외잔고수량
                ticker = stock.get('ovrs_pdno', stock.get('pdno', 'UNKNOWN'))
                qty_str = stock.get('ovrs_cblc_qty', stock.get('cblc_qty', '0'))
                qty = float(qty_str)
                
                # 수량이 0.0001 이상인 경우만 보유로 인정
                if qty <= 0:
                    continue

                # frcr_evlu_amt2: 외화평가금액2 (달러)
                eval_amt = float(stock.get('frcr_evlu_amt2', 0)) 
                
                # frcr_evlu_pfls_amt: 외화평가손익금액 (달러)
                pnl_amt = float(stock.get('frcr_evlu_pfls_amt', 0))
                
                # evlu_pfls_rt: 평가손익율 (%)
                pnl_rate = float(stock.get('evlu_pfls_rt', 0))
                
                stock_val_total += eval_amt
                total_pnl_amt += pnl_amt
                
                holding_list.append({
                    "code": ticker,
                    "qty": qty,
                    "val": eval_amt,
                    "pnl": pnl_rate,
                    "pnl_amt": pnl_amt
                })

        # 3. 총 자산 및 수익률 계산
        total_asset = usd_deposit + stock_val_total
        
        # 전체 포트폴리오 수익률 재계산
        total_stock_pnl_rate = 0.0
        if stock_val_total > 0:
            invested_principal = stock_val_total - total_pnl_amt
            if invested_principal > 0:
                total_stock_pnl_rate = (total_pnl_amt / invested_principal) * 100

        # [디버그 로그]
        print(f"\n [계좌] USD예수금: ${usd_deposit:.2f} | 주식평가: ${stock_val_total:.2f} | 종목수: {len(holding_list)}")

        return {
            "total": round(total_asset, 2),
            "cash": round(usd_deposit, 2), 
            "stock": round(stock_val_total, 2),
            "pnl": round(total_stock_pnl_rate, 2),
            "holdings": holding_list, 
            "currency": "USD"
        }

    except Exception as e:
        logging.error(f"[Account System Error] {e}")
        return None

def get_stock_qty(ticker):
    try:
        assets = get_my_total_assets()
        if assets and 'holdings' in assets:
            for h in assets['holdings']:
                if h['code'] == ticker:
                    return h['qty']
    except Exception as e:
        logging.error(f"[Account] Qty Check Error: {e}")
    
    return 0

if __name__ == "__main__":
    asset = get_my_total_assets()
    if asset:
        print(f"Asset Info: {asset}")