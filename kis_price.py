import requests
import json
import secret
import kis_auth

# === [머비스 설정] ===
# 기능: 미국 주식 현재 가격 조회
# 입력: 종목코드 (예: TSLA, AAPL)

def get_current_price(ticker):
    """
    특정 종목의 현재가(USD)를 조회하여 반환
    """
    access_token = kis_auth.get_access_token()
    if not access_token:
        return None

    # URL 설정 (해외주식 현재가)
    path = "uapi/overseas-price/v1/quotations/price"
    url = f"{secret.URL_MOCK}/{path}"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": secret.APP_KEY_MOCK,
        "appSecret": secret.APP_SECRET_MOCK,
        "tr_id": "HHDFS76200200"
    }

    # 거래소 코드는 편의상 나스닥(NAS)으로 고정, 추후 확장 가능
    params = {
        "AUTH": "",
        "EXCD": "NAS",
        "SYMB": ticker
    }
    
    # 조회 시도
    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        
        if data['rt_cd'] == '0':
            output = data['output']
            current_price = output['last'] # 현재가
            
            print(f"머비스: [{ticker}] 현재가는 {current_price} 달러입니다.")
            return float(current_price)
        else:
            print(f"머비스: 시세 조회 실패 ({data['msg1']})")
            return None

    except Exception as e:
        print(f"머비스: 시스템 오류 ({e})")
        return None

if __name__ == "__main__":
    # 테슬라(TSLA) 가격 확인 테스트
    price = get_current_price("TSLA")