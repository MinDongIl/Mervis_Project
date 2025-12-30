from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan
import json
import os
from datetime import datetime

# Google GenAI Client
client = genai.Client(api_key=secret.GEMINI_API_KEY)
MEMORY_FILE = "mervis_history.json"

# Load past memory
def load_memory(ticker):
    if not os.path.exists(MEMORY_FILE): return None
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if ticker in data and data[ticker]: return data[ticker][-1]
    except: return None
    return None

# Save current analysis to memory
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
    
    # Limit memory storage to last 30 items
    if len(data[ticker]) > 30: data[ticker] = data[ticker][-30:]
        
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Summarize raw list data into string
def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data available."
    
    df = pd.DataFrame(raw_data)
    
    # Normalize date column (xymd -> cymd)
    if 'xymd' in df.columns:
        df.rename(columns={'xymd': 'cymd'}, inplace=True)
    
    try:
        # Check essential columns
        if 'cymd' not in df.columns:
            return f"[{period_name}] Error: Date column missing. Keys: {list(df.columns)}"
            
        cols = ['cymd', 'clos']
        if 'rate' in df.columns: cols.append('rate')
            
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    except Exception as e:
        return f"[{period_name}] Data Parsing Error: {e}"

    # Sort descending to slice, then reverse for display
    df = df.head(limit).iloc[::-1]
    
    summary = [f"[{period_name} Trend]"]
    for _, row in df.iterrows():
        rate_info = f"({row['rate']}%)" if 'rate' in row else ""
        summary.append(f"- {row['cymd']}: ${row['clos']} {rate_info}")
    
    return "\n".join(summary)

# Generate Prompt and Call Gemini
def get_strategy_report(ticker, chart_data_set, is_open, past_memory):
    daily_txt = summarize_data(chart_data_set['daily'], "Daily", 10)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly", 8)
    monthly_txt = summarize_data(chart_data_set['monthly'], "Monthly", 12)
    yearly_txt = summarize_data(chart_data_set['yearly'], "Yearly", 24)

    current_price = chart_data_set['current_price']
    
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

    # 20 Analysis Guidelines
    guidelines = """
    1. Analyze trend (Bullish/Bearish).
    2. Check volatility.
    3. Identify Support & Resistance.
    4. Analyze Volume.
    5. Check Chart Patterns.
    6. Consider News/Events (Infer from data).
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
    1. Trend Analysis: Synthesize Year/Month/Day trends.
    2. Self-Reflection: Explicitly evaluate past memory accuracy.
    3. Strategy: Define specific Buy/Target/Stop prices.

    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Number only, $)
    목표가: (Number only, $)
    손절가: (Number only, $)
    기간: (e.g., 1 week)
    수익률: (e.g., 5%)
    확률: (e.g., 70%)
    코멘트: (Detailed analysis in Korean, citing the 4-timeframe data and guidelines.)
    """
    
    # [Debug] Save the actual prompt to file for verification
    try:
        with open(f"debug_prompt_{ticker}.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
    except: pass
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: Error generating content - {e}"

# Main Entry Point
def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    # Fetch Multi-Timeframe Data
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    # Update current price from latest data if needed
    if price == 0 and d_data:
        try:
            latest = d_data[0]
            # Handle both 'clos' and 'price' keys
            p_val = latest.get('clos') or latest.get('price') or latest.get('last')
            if p_val: price = float(p_val)
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