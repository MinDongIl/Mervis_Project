from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan
import json
import os
from datetime import datetime

# 머비스 두뇌 V9.3 - 데이터 키 호환성 강화 (xymd/cymd 자동 처리)

client = genai.Client(api_key=secret.GEMINI_API_KEY)
MEMORY_FILE = "mervis_history.json"

# 기억 로드 함수
def load_memory(ticker):
    if not os.path.exists(MEMORY_FILE): return None
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if ticker in data and data[ticker]: return data[ticker][-1]
    except: return None
    return None

# 기억 저장 함수
def save_memory(ticker, report):
    if "전략:" not in report: return
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = {"date": today, "report": report}
    
    data = {}
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f: data = json.load(f)
        except: data = {}
    
    if ticker not in data: data[ticker] = []
    data[ticker].append(entry)
    if len(data[ticker]) > 30: data[ticker] = data[ticker][-30:]
        
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 데이터 요약 함수 (수정됨: 키 호환성 처리)
def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data"
    
    df = pd.DataFrame(raw_data)
    
    # API별 날짜 컬럼명 호환 처리 (xymd -> cymd 통일)
    if 'xymd' in df.columns:
        df.rename(columns={'xymd': 'cymd'}, inplace=True)
    
    try:
        # 필수 컬럼 존재 여부 확인 및 형변환
        if 'cymd' not in df.columns:
            return f"[{period_name}] Date Column Error (Available: {list(df.columns)})"
            
        cols = ['cymd', 'clos']
        # 등락률(rate)이 없으면 계산 혹은 생략 처리
        if 'rate' in df.columns:
            cols.append('rate')
            
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    except Exception as e:
        return f"[{period_name}] Data Parsing Error: {e}"

    # 최신순 limit개 절사
    df = df.head(limit).iloc[::-1]
    
    summary = [f"[{period_name} Trend]"]
    for _, row in df.iterrows():
        rate_str = f"({row['rate']}%)" if 'rate' in row else ""
        summary.append(f"- {row['cymd']}: ${row['clos']} {rate_str}")
    
    return "\n".join(summary)

# 메인 분석 로직
def get_strategy_report(ticker, chart_data_set, is_open, past_memory):
    # 각 주기별 데이터 요약
    daily_txt = summarize_data(chart_data_set['daily'], "Daily", 10)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly", 8)
    monthly_txt = summarize_data(chart_data_set['monthly'], "Monthly", 12)
    yearly_txt = summarize_data(chart_data_set['yearly'], "Yearly", 24)

    current_price = chart_data_set['current_price']
    
    mem_ctx = ""
    if past_memory:
        mem_ctx = f"[Past Memory ({past_memory['date']})]\n{past_memory['report']}\n\n[Instruction] Evaluate the prediction above."
    else:
        mem_ctx = "[No Past Memory]"

    if is_open:
        status_msg = "Market Status: OPEN"
        mission = "Focus on real-time price action and immediate entry/exit points."
    else:
        status_msg = "Market Status: CLOSED"
        mission = "Analyze long-term trends to design entry strategies for the next open."

    # 분석 지침 (20가지 항목)
    guidelines = """
    1. Analyze trend (Bullish/Bearish).
    2. Check volatility.
    3. Identify Support & Resistance.
    4. Analyze Volume.
    5. Check Chart Patterns.
    6. Consider News/Events (Infer).
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

    prompt = f"""
    Role: AI Investment Partner 'Mervis'.
    {status_msg}
    
    Target: {ticker} (Current Price: ${current_price})

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
    1. Trend Analysis: Combine Long-term (Year/Month) and Short-term (Day).
    2. Self-Reflection: Evaluate past memory vs current reality.
    3. Strategy: Buy/Wait/Sell with specific prices.

    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Number only, $)
    목표가: (Number only, $)
    손절가: (Number only, $)
    기간: (e.g., 1 week)
    수익률: (e.g., 5%)
    확률: (e.g., 70%)
    코멘트: (Detailed analysis based on the 20 guidelines and 4-timeframe data. Use Korean.)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: {e}"

def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    if price == 0 and d_data:
        try:
            # 일봉 데이터에서도 키 호환성 처리
            latest = d_data[0]
            price_key = 'clos' if 'clos' in latest else 'price' # 혹시 모를 키 대응
            price = float(latest.get(price_key, 0))
        except: pass

    chart_set = {
        'daily': d_data,
        'weekly': w_data,
        'monthly': m_data,
        'yearly': y_data,
        'current_price': price
    }
    
    is_open = kis_scan.is_market_open()
    past_memory = load_memory(ticker)
    
    report = get_strategy_report(ticker, chart_set, is_open, past_memory)
    
    if "전략:" in report:
        save_memory(ticker, report)
    
    return {
        "code": ticker,
        "price": price,
        "report": report
    }