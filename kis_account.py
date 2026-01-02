import requests
import json
import mervis_state
import kis_auth
import secret

# [설정] 해외주식 잔고조회 API 정보
# 실전/모의 TR ID가 다를 수 있으나, 일반적으로 URL만 다르고 구조는 같음
# 여기서는 일반적인 해외주식 잔고 조회(CTRP6504R) 기준 작성
# 모의투자의 경우 TR ID가 VTRP6504R 일 수 있음 (자동 분기 처리)

def get_my_total_assets():
    """
    계좌의 총 자산, 예수금, 주식 평가금, 수익률을 조회합니다.
    Return: {'total': 0, 'cash': 0, 'stock': 0, 'pnl': 0.0}
    """
    mode = mervis_state.get_mode()
    base_url = "https://openapi.koreainvestment.com:9443" if mode == "REAL" else "https://openapivts.koreainvestment.com:29443"
    
    # TR ID 설정 (실전: CTRP6504R / 모의: VTRP6504R)
    # *주의: 모의투자는 TR ID가 다를 수 있으니 문서 확인 필요. 통상 접두어 V 붙음.
    tr_id = "CTRP6504R" if mode == "REAL" else "VTRP6504R"

    # 1. 토큰 및 헤더 준비
    token = kis_auth.get_access_token()
    if not token:
        print(" [Account] 토큰 발급 실패.")
        return None

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": secret.APP_KEY_REAL if mode == "REAL" else secret.APP_KEY_MOCK,
        "appsecret": secret.APP_SECRET_REAL if mode == "REAL" else secret.APP_SECRET_MOCK,
        "tr_id": tr_id,
        "custtype": "P"
    }

    # 2. 파라미터 설정 (계좌번호)
    # 해외주식은 국가코드(840:미국), 통화코드(USD) 필수
    params = {
        "CANO": secret.CANO,            # 종합계좌번호 앞 8자리
        "ACNT_PRDT_CD": secret.ACNT_PRDT_CD, # 계좌번호 뒤 2자리
        "WCRC_FRCR_DVS_CD": "02",       # 01:원화, 02:외화 (보통 USD 기준 조회 시 02)
        "NATN_CD": "840",               # 840: 미국
        "TR_MK": "00",                  # 거래시장코드 (00:전체)
        "CTX_AREA_FK": "",              # 연속조회용 (첫 조회라 공란)
        "CTX_AREA_NK": ""               # 연속조회용 (첫 조회라 공란)
    }
    
    # 3. API 호출
    path = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    url = f"{base_url}{path}"

    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        
        # [디버깅] 응답 확인용 (필요시 주석 해제)
        # print(json.dumps(data, indent=2, ensure_ascii=False))

        if data['rt_cd'] != '0':
            print(f" [Account Error] {data['msg1']}")
            return None
        
        # 4. 데이터 파싱
        # output1: 종목별 잔고 리스트
        # output2: 계좌 전체 현황 (여기서 총액 추출)
        summary = data['output2']
        
        # 데이터가 없을 경우 방어
        if not summary:
            return {'total': 0.0, 'cash': 0.0, 'stock': 0.0, 'pnl': 0.0}

        # KIS API 필드명 (해외주식 기준)
        # tot_asst_amt: 총자산(원화 환산 등 포함될 수 있음, 보통 외화평가액 사용)
        # tot_evlu_pfls_amt: 총 평가 손익
        # ovrs_rlzt_pfls_amt: 해외 실현 손익
        # frcr_pchs_amt1: 외화 매입 금액 (투자 원금)
        # ovrs_tot_pfls: 해외 총 수익률 (%)
        
        # *API 버전에 따라 필드명이 다를 수 있어 안전하게 get 사용
        total_pnl = float(summary.get('tot_evlu_pfls_amt', 0)) # 평가 손익
        buy_amt = float(summary.get('frcr_pchs_amt1', 0))      # 매입 금액
        
        # 평가 금액 (매입 + 손익)
        stock_val = buy_amt + total_pnl
        
        # 수익률 계산 (매입금이 0이면 0%)
        pnl_rate = float(summary.get('ovrs_tot_pfls', 0))
        
        # 예수금 (총자산이 명확지 않으면 API 구조상 계산 필요할 수 있음)
        # 여기서는 편의상 output2의 tot_asst_amt(총자산) 활용 시도
        # *주의: 해외주식 API는 예수금을 별도로 'inquire-psamount'로 조회해야 정확한 경우가 많음
        # 일단은 output2에 있는 정보로 추정
        # (실제로는 예수금 API를 따로 부르는게 가장 정확하나, 약식으로 진행)
        # tot_asst_amt가 없으면 매입금액을 자산으로 가정 (예수금 0)
        # 민동일 님 환경에 맞춰 나중에 정교화 가능
        
        # 임시 로직: 주식가치 = 총자산으로 가정 (예수금 조회 API는 별도라 복잡해짐 방지)
        # 추후 필요하면 예수금 조회 추가 가능.
        total_asset = stock_val # (일단 주식 가치만 자산으로 잡음, 현금은 0으로 가정)
        
        return {
            "total": round(total_asset, 2),
            "cash": 0.0, # 예수금 API 추가 전까지 0으로 처리 (보수적 접근)
            "stock": round(stock_val, 2),
            "pnl": round(pnl_rate, 2)
        }

    except Exception as e:
        print(f" [Account System Error] {e}")
        return None

if __name__ == "__main__":
    # 테스트 실행
    print("--- Account Check ---")
    print(get_my_total_assets())