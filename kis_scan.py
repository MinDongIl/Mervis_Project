import requests
import secret
import kis_auth
import mervis_state
from datetime import datetime, time
import pytz
import json
import random # [NEW] 랜덤 셔플을 위해 추가

def is_market_open():
    try:
        ny_tz = pytz.timezone('US/Eastern')
        ny_now = datetime.now(ny_tz)
        if ny_now.weekday() >= 5: return False
        curr = ny_now.time()
        return time(9, 30) <= curr <= time(16, 0)
    except:
        return False

def get_market_rank(excd, gubun, count=10):
    token = kis_auth.get_access_token()
    if not token: return []

    mode = mervis_state.get_mode()
    if mode == "MOCK": return []

    base_url = secret.URL_REAL
    app_key = secret.APP_KEY_REAL
    app_secret = secret.APP_SECRET_REAL
    tr_id = "HHDFS76410000"
    
    path = "uapi/overseas-price/v1/quotations/inquire-search"
    url = f"{base_url}/{path}"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P"
    }
    
    params = {
        "AUTH": "", "EXCD": excd, "GUBN": gubun, "COND": "0", 
        "INQR_STRT_CRTI": "", "INQR_END_CRTI": "", "VOL_TNTE": "",
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            rank_list = data.get('output')
            if not rank_list: return []

            targets = []
            for item in rank_list[:count]:
                price = float(item.get('last') or item.get('price') or 0)
                vol = int(item.get('vol') or item.get('acml_vol') or 0)
                if price < 1.0 or vol == 0: continue
                targets.append({
                    "code": item['symb'], "name": item['name'],
                    "price": price, "diff": item['rate'],
                    "market": excd, "reason": gubun
                })
            return targets
        return []
    except: return []

def get_dynamic_targets():
    is_open = is_market_open()
    status = "OPEN" if is_open else "CLOSED"
    mode = mervis_state.get_mode()
    print(f"[Mervis] Market Status: {status} ({mode} Mode)")

    if mode == "MOCK":
        print("\n[Info] Mock Server: Loading Massive Universe.")
        return _get_massive_universe()

    print(f"[Mervis] Mining Wide-Range data from Real Server...")

    targets = {}
    markets = ["NAS", "NYS"]
    conditions = [("0", "Volume"), ("1", "Rise"), ("2", "Fall"), ("3", "Amount")]
    
    success_cnt = 0
    for mkt in markets:
        print(f" -> Scanning {mkt}...", end=" ")
        for cond_code, cond_name in conditions:
            raw_list = get_market_rank(mkt, cond_code, 10)
            if raw_list:
                success_cnt += 1
                print(f"[{cond_name}:{len(raw_list)}]", end=" ")
                for item in raw_list:
                    if item['code'] not in targets:
                        item['tag'] = f"{mkt} {cond_name}"
                        targets[item['code']] = item
                    else:
                        targets[item['code']]['tag'] += f"/{cond_name}"
            else:
                print(f"[{cond_name}:0]", end=" ")
        print("") 

    final_list = list(targets.values())

    # [핵심] 스캔 결과가 부실하면(5개 미만), 매시브 유니버스 발동
    if len(final_list) < 5:
        print("\n[Warning] Live Scan insufficient. Activating 'Massive Universe Protocol'.")
        print("[Action] Loading Top 100 Global Market Leaders by Sector.")
        return _get_massive_universe()
            
    else:
        print(f"\n[Mervis] Scan complete. Total {len(final_list)} targets.")

    return final_list

# [NEW] 글로벌 시장을 장악하는 100대 종목 리스트
def _get_massive_universe():
    universe = []
    
    # 1. 매그니피센트 7 + 빅테크 (시장의 심장)
    big_tech = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AVGO", "ORCL", "ADBE", "CRM"]
    
    # 2. 반도체 & AI 하드웨어 (가장 뜨거운 섹터)
    semi = ["AMD", "INTC", "QCOM", "MU", "TSM", "ARM", "ASML", "AMAT", "LRCX", "SMCI"]
    
    # 3. 레버리지/인버스 ETF (야수의 심장 - 변동성 학습용)
    etf_vol = ["TQQQ", "SQQQ", "SOXL", "SOXS", "BULZ", "BERZ", "FNGU", "FNGD", "LABU"]
    
    # 4. 바이오 & 헬스케어 (미래 성장)
    bio = ["LLY", "NVO", "PFE", "MRK", "JNJ", "ABBV", "AMGN", "BIIB", "ISRG"]
    
    # 5. 방산 & 우주 & 산업재 (지정학적 리스크 대비)
    defense = ["LMT", "RTX", "BA", "GE", "CAT", "DE", "HON"]
    
    # 6. 금융 & 비트코인 (자금의 흐름)
    finance = ["JPM", "BAC", "V", "MA", "GS", "MS", "BLK", "COIN", "MSTR", "HOOD", "PYPL"]
    
    # 7. 소비재 & 리테일 (실물 경제)
    consumer = ["WMT", "COST", "TGT", "KO", "PEP", "MCD", "SBUX", "NKE", "HD"]
    
    # 8. 에너지 & 원자재
    energy = ["XOM", "CVX", "OXY", "SLB", "FCX", "AA"]
    
    # 9. 거시경제 ETF (채권, 금, 은, 공포지수)
    macro = ["TLT", "TMF", "SPY", "QQQ", "DIA", "IWM", "GLD", "SLV", "VIXY"]

    # 전체 통합
    full_list = big_tech + semi + etf_vol + bio + defense + finance + consumer + energy + macro
    
    # 중복 제거
    full_list = list(set(full_list))
    
    # [전략] 한 번에 100개를 다 분석하면 시간이 너무 오래 걸림 (개당 3초 * 100 = 5분 소요)
    # 따라서, 매 실행 시 '무작위로 30개'를 뽑아서 집중 분석하거나,
    # 사용자가 원하면 전체를 다 돌리도록 설정 가능.
    # 여기서는 '다양성'을 위해 랜덤으로 40개를 뽑아서 분석하도록 설정.
    
    selected_targets = random.sample(full_list, min(len(full_list), 40))
    
    # Universe 태그 달아서 리턴
    for code in selected_targets:
        universe.append({"code": code, "name": "Universe", "price": 0, "tag": "Global_Tier1"})
        
    print(f"[System] Selected {len(universe)} targets from {len(full_list)} massive pool.")
    return universe