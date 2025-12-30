from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan
import json
import os
from datetime import datetime
import mervis_profile
import mervis_state 
import mervis_news     # [기존 유지] 뉴스 모듈
import mervis_bigquery # [NEW] BigQuery 모듈 연결

client = genai.Client(api_key=secret.GEMINI_API_KEY)

# [기존 유지] BigQuery에서 기억 불러오기
def load_memory(ticker):
    memory = mervis_bigquery.get_recent_memory(ticker)
    if memory:
        return memory
    return None

# [기존 유지] BigQuery에 기억 저장하기
def save_memory(ticker, price, report, news_data):
    if "전략:" not in report: return
    mode = mervis_state.get_mode()
    mervis_bigquery.save_log(ticker, mode, price, report, news_data)

# [기존 유지] 데이터 요약
def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data available."
    
    df = pd.DataFrame(raw_data)
    
    if 'xymd' in df.columns:
        df.rename(columns={'xymd': 'cymd'}, inplace=True)
    
    try:
        if 'cymd' not in df.columns:
            return f"[{period_name}] Error: Date column missing. Keys: {list(df.columns)}"
            
        cols = ['cymd', 'clos']
        if 'rate' in df.columns: cols.append('rate')
            
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    except Exception as e:
        return f"[{period_name}] Data Parsing Error: {e}"

    df = df.head(limit).iloc[::-1]
    
    summary = [f"[{period_name} Trend]"]
    for _, row in df.iterrows():
        rate_info = f"({row['rate']}%)" if 'rate' in row else ""
        summary.append(f"- {row['cymd']}: ${row['clos']} {rate_info}")
    
    return "\n".join(summary)

# [업데이트] 거래량 정보(volume_info) 인자 추가 및 프롬프트 반영
def get_strategy_report(ticker, chart_data_set, is_open, past_memory, news_data):
    daily_txt = summarize_data(chart_data_set['daily'], "Daily", 10)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly", 8)
    monthly_txt = summarize_data(chart_data_set['monthly'], "Monthly", 12)
    yearly_txt = summarize_data(chart_data_set['yearly'], "Yearly", 24)

    current_price = chart_data_set['current_price']
    # [V11.6 NEW] 거래량 정보 가져오기
    volume_info = chart_data_set.get('volume_info', 'Volume: Data Unavailable')
    
    user_profile = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_profile, indent=2, ensure_ascii=False)

    mem_ctx = ""
    if past_memory:
        mem_ctx = f"[Past Memory ({past_memory['date']})]\n{past_memory['report']}\n\n[Instruction] Review the past prediction against current data."
    else:
        mem_ctx = "[No Past Memory]"

    if is_open:
        status_msg = "Market Status: OPEN (Live Trading)"
        mission = "Provide real-time actionable strategy (Entry/Exit/Wait)."
    else:
        status_msg = "Market Status: CLOSED (Post-Market)"
        mission = "Analyze long-term trends and prepare a strategy for the next open."

    guidelines = """
    1. Analyze trend (Bullish/Bearish).
    2. Check volatility.
    3. Identify Support & Resistance.
    4. **Analyze Volume**: Refer to the provided 'Volume Data'. If real-time volume is missing, use the 'Last Close Volume' as a proxy for liquidity.
    5. Check Chart Patterns.
    6. **Analyze News/Events**: MUST incorporate the provided [Recent News & Issues] into the strategy.
    7. Market Sentiment.
    8. Investor Psychology.
    9. Compare with Peers.
    10. Market Trend.
    11. Buy/Sell Patterns.
    12. Correlation with Peers.
    13. Market Liquidity.
    14. Institutional Moves.
    15. Macroeconomics.
    16. Other Participants.
    17. Psychological Factors.
    18. Technical Indicators.
    19. Other Correlations.
    20. Key Technical Indicators.
    """

    # [업데이트] 거래량 정보({volume_info})가 포함된 프롬프트
    prompt = f"""
    Role: AI Investment Partner 'Mervis'.
    {status_msg}
    
    Target: {ticker} (Current Price: ${current_price})
    {volume_info}
    
    [User Profile (Target Persona)]
    {profile_str}

    [Recent News & Issues (Real-time)]
    {news_data}

    [Timeframe Data]
    1. {yearly_txt}
    2. {monthly_txt}
    3. {weekly_txt}
    4. {daily_txt}

    {mem_ctx}
    
    [Mission]
    {mission}

    [Guidelines]
    {guidelines}

    [Requirements]
    1. Trend Analysis: Synthesize Year/Month/Day trends.
    2. Self-Reflection: Explicitly evaluate past memory accuracy.
    3. **Personalization**: Check if this stock aligns with the [User Profile]. 
       - If the user is 'Conservative' and the stock is highly volatile, provide a WARNING.
       - If the stock matches the user's 'Goals', highlight it.
    4. **News Integration**: You MUST mention specific keywords from the [Recent News] to justify your decision.
    5. Strategy: Define specific Buy/Target/Stop prices.

    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Number only, $)
    목표가: (Number only, $)
    손절가: (Number only, $)
    기간: (e.g., 1 week)
    수익률: (e.g., 5%)
    확률: (e.g., 70%)
    코멘트: (Detailed analysis in Korean. Include 'News Analysis' and 'Profile Match' sections.)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: Error generating content - {e}"

# [업데이트] 거래량 보정 로직 추가
def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    # 차트 데이터 수집
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    # [V11.6 NEW] 데이터 보정용 최신 일봉
    latest_daily = d_data[0]

    # 1. 가격 보정
    if price == 0 and d_data:
        try:
            p_val = latest_daily.get('clos') or latest_daily.get('price') or latest_daily.get('last')
            if p_val: price = float(p_val)
        except: pass

    # 2. 거래량 보정 (Fallback Logic)
    volume_info = "Volume Data: Real-time volume unavailable."
    try:
        # KIS 일봉 데이터에서 누적 거래량(acml_vol) 확인
        last_vol = latest_daily.get('acml_vol') or latest_daily.get('vol')
        if last_vol:
             volume_info = f"Volume Data: Real-time unavailable. Reference Last Close Volume: {last_vol}"
    except:
        pass

    chart_set = {
        'daily': d_data,
        'weekly': w_data,
        'monthly': m_data,
        'yearly': y_data,
        'current_price': price,
        'volume_info': volume_info # [NEW] 프롬프트로 전달
    }
    
    print(f" [News] Fetching latest info for {ticker}...", end="")
    news_data = mervis_news.get_stock_news(ticker)
    
    is_open = kis_scan.is_market_open()
    
    # BigQuery에서 로드
    past_memory = load_memory(ticker)
    
    # 분석 요청
    report = get_strategy_report(ticker, chart_set, is_open, past_memory, news_data)
    
    if "전략:" in report:
        # BigQuery에 저장
        save_memory(ticker, price, report, news_data)
        print(" [DB] Saved to BigQuery.")
    
    return {
        "code": ticker,
        "price": price,
        "report": report
    }