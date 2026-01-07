import yfinance as yf
import pandas as pd

def get_fundamental_info(ticker):
    """
    [가치투자] yfinance를 통해 펀더멘털 및 컨센서스 데이터 조회
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info or 'regularMarketPrice' not in info:
            return None, "데이터 조회 실패"

        # 1. 기초 밸류에이션
        valuation = {
            "market_cap": info.get('marketCap', 0),
            "trailing_pe": info.get('trailingPE', 0), # 현재 PER
            "forward_pe": info.get('forwardPE', 0),   # 선행 PER (미래 실적 기준)
            "pb_ratio": info.get('priceToBook', 0),
            "roe": info.get('returnOnEquity', 0)
        }

        # 2. 성장성 (매출/이익 성장률)
        growth = {
            "revenue_growth": info.get('revenueGrowth', 0), # 매출 성장률
            "earnings_growth": info.get('earningsGrowth', 0) # 이익 성장률
        }

        # 3. 컨센서스 (애널리스트 의견)
        consensus = {
            "target_mean": info.get('targetMeanPrice', 0), # 목표가 평균
            "recommendation": info.get('recommendationKey', 'none'), # buy, hold, sell
            "number_of_analysts": info.get('numberOfAnalystOpinions', 0)
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
    if val['forward_pe'] > 0 and val['trailing_pe'] > 0:
        if val['forward_pe'] < val['trailing_pe']:
            factors.append("Earnings_Growth_Expected")
            summary_parts.append(f"PE improving ({val['trailing_pe']:.1f} -> {val['forward_pe']:.1f})")

    # 2. [컨센서스 분석] 목표가 괴리율
    curr_price = yf.Ticker(ticker).fast_info['last_price']
    if con['target_mean'] > curr_price * 1.1: # 목표가가 현재가보다 10% 이상 높으면
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