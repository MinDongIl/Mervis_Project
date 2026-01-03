import requests
import json
import mervis_state
import kis_auth
import secret

# [설정] 해외주식 잔고 및 자산 조회 통합 모듈

def _get_api_config():
    """모드에 따른 API 설정값 반환"""
    mode = mervis_state.get_mode()
    
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
        # secret.py 변수명 불일치 오류 방지 (CANO vs CANO_REAL)
        # 사용자 환경에 맞춰 안전하게 매핑
        cano = getattr(secret, 'CANO_REAL', getattr(secret, 'CANO', ''))
        prdt = getattr(secret, 'ACNT_PRDT_CD_REAL', getattr(secret, 'ACNT_PRDT_CD', ''))
        # TR ID (실전용)
        tr_id_balance = "CTRP6504R"  # 계좌 잔고(자산)
        tr_id_stock = "VTTS3012R"    # (주의) 주식 잔고는 보통 JTTT3012R(매도) 등 거래용과 다름, 단순 조회는 inquire-balance 참조
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK
        cano = getattr(secret, 'CANO_MOCK', '')
        prdt = getattr(secret, 'ACNT_PRDT_CD_MOCK', '')
        # TR ID (모의용)
        tr_id_balance = "VTRP6504R"  # 계좌 잔고(자산) (접두어 V 확인 필요)
        tr_id_stock = "VTTS3012R"    # 모의투자용

    return {
        "mode": mode,
        "base_url": base_url,
        "app_key": app_key,
        "app_secret": app_secret,
        "cano": cano,
        "prdt": prdt,
        "tr_id_balance": tr_id_balance,
        "tr_id_stock": tr_id_stock
    }

def get_my_total_assets():
    """
    [통합 자산 조회]
    계좌의 총 자산, 평가금, 수익률 조회
    Return: {'total': 0, 'cash': 0, 'stock': 0, 'pnl': 0.0}
    """
    config = _get_api_config()
    token = kis_auth.get_access_token()
    
    if not token:
        print(" [Account] 토큰 발급 실패.")
        return None

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": config['app_key'],
        "appsecret": config['app_secret'],
        "tr_id": config['tr_id_balance'], # 자산 조회용 TR
        "custtype": "P"
    }

    params = {
        "CANO": config['cano'],
        "ACNT_PRDT_CD": config['prdt'],
        "WCRC_FRCR_DVS_CD": "02",   # 02: 외화(USD) 기준
        "NATN_CD": "840",           # 840: 미국
        "TR_MK": "00",
        "CTX_AREA_FK": "",
        "CTX_AREA_NK": ""
    }

    path = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    url = f"{config['base_url']}{path}"

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()

        if data['rt_cd'] != '0':
            print(f" [Account Error] {data['msg1']}")
            return None
        
        summary = data['output2']
        if not summary:
            return {'total': 0.0, 'cash': 0.0, 'stock': 0.0, 'pnl': 0.0}

        # 데이터 파싱 (안전하게 get 사용)
        total_pnl = float(summary.get('tot_evlu_pfls_amt', 0)) # 평가 손익
        buy_amt = float(summary.get('frcr_pchs_amt1', 0))      # 매입 금액
        
        stock_val = buy_amt + total_pnl
        pnl_rate = float(summary.get('ovrs_tot_pfls', 0))
        
        # 임시: 예수금(cash)은 별도 API 필요하므로 일단 0 혹은 잔여 예수금 필드가 있다면 매핑
        # output2에 dncl_amt(예수금) 등이 있는지 확인 필요하나, 해외주식은 보통 별도.
        # 보수적으로 주식 가치 = 총 자산으로 잡음.
        
        return {
            "total": round(stock_val, 2),
            "cash": 0.0, 
            "stock": round(stock_val, 2),
            "pnl": round(pnl_rate, 2)
        }

    except Exception as e:
        print(f" [Account System Error] {e}")
        return None

def get_stock_qty(ticker):
    """
    [특정 종목 잔고 조회]
    특정 티커(ticker)의 보유 수량을 리턴합니다. (매도 시 확인용)
    Return: (int) 수량
    """
    config = _get_api_config()
    token = kis_auth.get_access_token()
    if not token: return 0
    
    # 잔고 조회 API (inquire-balance)를 재활용하거나 별도 TR을 쓸 수 있음.
    # inquire-present-balance (위에서 쓴거)의 output1을 뒤지면 됨.
    
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": config['app_key'],
        "appsecret": config['app_secret'],
        "tr_id": config['tr_id_balance'], # 같은 API 써도 됨
        "custtype": "P"
    }

    params = {
        "CANO": config['cano'],
        "ACNT_PRDT_CD": config['prdt'],
        "WCRC_FRCR_DVS_CD": "02",
        "NATN_CD": "840",
        "TR_MK": "00",
        "CTX_AREA_FK": "",
        "CTX_AREA_NK": ""
    }
    
    path = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    url = f"{config['base_url']}{path}"

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()
        
        if data['rt_cd'] == '0':
            # output1: 보유 종목 리스트
            for item in data['output1']:
                # ovrs_pdno: 종목코드 (티커)
                if item['ovrs_pdno'] == ticker:
                    # cblc_qty13 or ovrs_cblc_qty : 잔고수량 (API마다 다름, 보통 ord_psbl_qty(주문가능) 확인)
                    # 여기선 ccld_qty_smtl1(체결수량합계) 혹은 ord_psbl_qty(주문가능수량)을 봐야함.
                    # 안전하게 'ord_psbl_qty'(주문가능수량)을 리턴
                    return int(float(item.get('ord_psbl_qty', 0)))
        return 0
    except:
        return 0

if __name__ == "__main__":
    print("--- Account Info ---")
    print(get_my_total_assets())
    # print("Tesla Qty:", get_stock_qty("TSLA"))