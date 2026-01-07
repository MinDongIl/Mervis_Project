import yfinance as yf

def get_supply_info(ticker):
    """
    [Data Fetcher] yfinance를 통해 수급 기초 데이터 조회
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 데이터가 없을 경우 방어 로직
        supply_data = {
            "institution_pct": info.get('heldPercentInstitutions', 0), # 기관 보유 비중 (0.8 = 80%)
            "insider_pct": info.get('heldPercentInsiders', 0),         # 내부자 보유 비중
            "short_ratio": info.get('shortRatio', 0),                  # 공매도 비율
            "float_shares": info.get('floatShares', 0)                 # 유통 주식 수
        }
        
        # None 타입 방지 (0으로 치환)
        for k, v in supply_data.items():
            if v is None: supply_data[k] = 0.0
            
        return supply_data, None
    except Exception as e:
        return None, f"Supply Error: {e}"

def analyze_supply_structure(ticker):
    """
    [Static Analysis] 현재 종목의 수급 구조(안정성)만 분석
    """
    data, err = get_supply_info(ticker)
    if err: return {}, err, []

    factors = []
    
    inst_pct = data['institution_pct']
    short_ratio = data['short_ratio']

    # 1. [메이저 수급] 기관 비중이 60% 이상 (안정적)
    if inst_pct > 0.6:
        factors.append("High_Institutional_Ownership")
    elif inst_pct < 0.1:
        factors.append("Retail_Dominant") # 개미 위주 (변동성 큼)

    # 2. [숏스퀴즈] 공매도 비율 경고
    if short_ratio > 5:
        factors.append("High_Short_Interest")

    return data, None, factors

def analyze_hybrid_supply(supply_data, tech_signals):
    """
    [Hybrid Analysis] 기술적 신호(거래량)와 수급 구조를 결합하여 판단
    - tech_signals: technical.py에서 감지한 신호 리스트 (예: ['Volume_Spike', 'Price_Above_VWAP'])
    """
    if not supply_data: return "No Data"
    
    inst_pct = supply_data.get('institution_pct', 0)
    is_vol_spike = 'Volume_Spike' in tech_signals
    is_vwap_support = 'Price_Above_VWAP' in tech_signals
    
    conclusion = "Neutral"
    
    # 시나리오 1: 기관 비중 높은 놈이 거래량 터짐 -> "찐 수급"
    if inst_pct > 0.5 and is_vol_spike:
        conclusion = "Institutions_Buying (Reliable)"
        if is_vwap_support:
            conclusion += " + VWAP Support"
            
    # 시나리오 2: 잡주(기관 없음)가 거래량 터짐 -> "개미/세력 펌핑"
    elif inst_pct < 0.1 and is_vol_spike:
        conclusion = "Speculative_Pump (High Risk)"
        
    # 시나리오 3: 공매도 비율 높은데 거래량 터짐 -> "숏 스퀴즈 가능성"
    elif supply_data.get('short_ratio', 0) > 5 and is_vol_spike:
        conclusion = "Potential_Short_Squeeze"
        
    return conclusion