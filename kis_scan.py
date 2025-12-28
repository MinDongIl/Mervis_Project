import requests
import secret
import kis_auth
import mervis_state
from datetime import datetime, time
import pytz
import json # json 모듈 명시

def is_market_open():
    try:
        ny_tz = pytz.timezone('US/Eastern')
        ny_now = datetime.now(ny_tz)
        if ny_now.weekday() >= 5: return False
        curr = ny_now.time()
        return time(9, 30) <= curr <= time(16, 0)
    except:
        return False

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
        
        # [수정] 응답이 JSON이 아닐 경우(점검 중) 처리
        try:
            data = res.json()
        except json.JSONDecodeError:
            print(f"   [서버응답확인] JSON 변환 실패. 서버가 HTML 또는 텍스트를 반환했습니다.")
            print(f"   [내용미리보기] {res.text[:100]}") # 앞 100글자만 출력해서 확인
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
            # API 에러 코드 반환 시
            print(f"   [API오류] {data['msg1']} (Code: {data['rt_cd']})")
            
        return targets

    except Exception as e:
        print(f"   [통신오류] {e}")
        return []

def get_dynamic_targets():
    is_open = is_market_open()
    status = "개장(Live)" if is_open else "휴장(Closed)"
    print(f"[머비스] 시장 상태: {status}")
    print(f"[머비스] 트렌드 데이터 마이닝 시도...")

    targets = {}
    
    markets = ["NAS", "NYS"]
    conditions = [("0", "거래량"), ("1", "상승")] # 하락은 일단 제외하고 테스트
    
    success_scan = False
    
    for mkt in markets:
        for cond_code, cond_name in conditions:
            raw_list = get_market_rank(mkt, cond_code, 15)
            if raw_list:
                success_scan = True
                print(f"   -> [{mkt}] {cond_name}: {len(raw_list)}개 확보")
                
            for item in raw_list:
                if item['code'] not in targets:
                    item['tag'] = f"{mkt} {cond_name}"
                    targets[item['code']] = item

    final_list = list(targets.values())

    # [비상 대책] 서버 점검 등으로 데이터가 0건일 때 -> AI 테스트를 위해 학습용 리스트 로드
    if not final_list:
        print("\n[경고] 증권사 서버 점검 또는 휴장으로 인해 '실시간 트렌드' 조회 불가.")
        print("[조치] 머비스의 기능을 테스트하기 위해 '필수 학습 리스트'를 로드합니다.")
        
        # 민동일 님의 '학습'을 위해 서버 점검 시간에만 작동하는 리스트
        universe = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "AMD", "QQQ", "SPY", "SOXL"]
        
        for code in universe:
            final_list.append({"code": code, "name": "Universe", "price": 0})
            
    else:
        print(f"\n[머비스] 동적 스캔 완료. 총 {len(final_list)}개 트렌드 종목 확보.")

    return final_list