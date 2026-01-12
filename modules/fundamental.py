import yfinance as yf
import pandas as pd

# 안전한 숫자 변환 헬퍼 함수
def safe_float(value):
    """
    API에서 온 값이 None, 'N/A', 문자열일 경우 0.0으로 변환하여
    비교 연산 시 TypeError가 나는 것을 방지함
    """
    try:
        if value is None: return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def get_fundamental_info(ticker):
    """
    [가치투자] yfinance를 통해 펀더멘털 및 컨센서스 데이터 조회
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # yfinance 버전 이슈 대비: regularMarketPrice가 없으면 currentPrice 확인
        if not info:
            return None, "데이터 조회 실패"
        
        # 필수 키 확인 (없어도 죽지 않도록 로직 완화)
        if 'regularMarketPrice' not in info and 'currentPrice' not in info:
            pass # 일단 진행

        # 1. 기초 밸류에이션 (safe_float 적용)
        valuation = {
            "market_cap": safe_float(info.get('marketCap')),
            "trailing_pe": safe_float(info.get('trailingPE')), # 현재 PER
            "forward_pe": safe_float(info.get('forwardPE')),   # 선행 PER (미래 실적 기준)
            "pb_ratio": safe_float(info.get('priceToBook')),
            "roe": safe_float(info.get('returnOnEquity'))
        }

        # 2. 성장성 (매출/이익 성장률)
        growth = {
            "revenue_growth": safe_float(info.get('revenueGrowth')),
            "earnings_growth": safe_float(info.get('earningsGrowth'))
        }

        # 3. 컨센서스 (애널리스트 의견)
        consensus = {
            "target_mean": safe_float(info.get('targetMeanPrice')), # 목표가 평균
            "recommendation": info.get('recommendationKey', 'none'), # 문자열 유지
            "number_of_analysts": safe_float(info.get('numberOfAnalystOpinions'))
        }

        return {
            "valuation": valuation,
            "growth": growth,
            "consensus": consensus
        }, None

    except Exception as e:
        return None, f"Fundamental Error: {e}"

def analyze_fundamentals(ticker, active_strategies=None):
    """
    Brain에서 호출하는 메인 함수
    """
    data, err = get_fundamental_info(ticker)
    if err: return {}, err, []

    factors = []
    summary_parts = []
    
    val = data['valuation']
    gro = data['growth']
    con = data['consensus']

    # 1. [저평가 분석] 선행 PER이 현재 PER보다 낮으면 (이익 증가 예상)
    # safe_float 덕분에 이제 안전하게 숫자 비교 가능
    if val['forward_pe'] > 0 and val['trailing_pe'] > 0:
        if val['forward_pe'] < val['trailing_pe']:
            factors.append("Earnings_Growth_Expected")
            summary_parts.append(f"PE improving ({val['trailing_pe']:.1f} -> {val['forward_pe']:.1f})")

    # 2. [컨센서스 분석] 목표가 괴리율
    try:
        # fast_info 접근 시 오류 방지
        fi = yf.Ticker(ticker).fast_info
        curr_price = fi.get('last_price', 0) if hasattr(fi, 'get') else fi['last_price']
    except:
        curr_price = 0

    if curr_price > 0 and con['target_mean'] > curr_price * 1.1: # 목표가가 현재가보다 10% 이상 높으면
        factors.append("Analyst_Upside_Potential")
        summary_parts.append(f"Target ${con['target_mean']} (Upside)")

    # 3. [강력 매수 의견]
    if con['recommendation'] in ['buy', 'strong_buy']:
        factors.append("WallStreet_Buy_Rating")

    summary_text = f"""
    [Fundamental Analysis]
    Market Cap: ${val['market_cap']:,}
    Recommendation: {con['recommendation'].upper()} (Target: ${con['target_mean']})
    Growth: Rev {gro['revenue_growth']*100:.1f}%, Earn {gro['earnings_growth']*100:.1f}%
    Key Factors: {', '.join(factors)}
    """

    return data, None, factors