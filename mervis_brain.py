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
import mervis_news 
import mervis_bigquery 

client = genai.Client(api_key=secret.GEMINI_API_KEY)
# secret.py에 USER_NAME = "이름" 설정 필수
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

def load_memories(ticker):
    memories = mervis_bigquery.get_multi_memories(ticker, limit=3)
    return memories if memories else []

def save_memory(ticker, price, report, news_data):
    if "전략:" not in report: return
    mode = mervis_state.get_mode()
    mervis_bigquery.save_log(ticker, mode, price, report, news_data)

def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data available."
    df = pd.DataFrame(raw_data)
    if 'xymd' in df.columns:
        df.rename(columns={'xymd': 'cymd'}, inplace=True)
    
    try:
        required_cols = ['clos', 'open', 'high', 'low']
        for col in required_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df['cymd'] = df['cymd'].astype(str)
    except Exception as e:
        return f"[{period_name}] Data Parsing Error: {e}"

    df = df.head(limit).iloc[::-1]
    summary = [f"[{period_name} Candlestick & Trend]"]
    
    if len(df) >= 5:
        ma5 = df['clos'].rolling(window=5).mean().iloc[-1]
        current_price = df['clos'].iloc[-1]
        disparity = (current_price / ma5) * 100 if ma5 > 0 else 100
        summary.append(f"- Technical Insight: 5-Day MA disparity is {disparity:.2f}%")

    for _, row in df.iterrows():
        candle_info = f"O:${row['open']} H:${row['high']} L:${row['low']} C:${row['clos']}"
        summary.append(f"- {row['cymd']}: {candle_info}")
    
    return "\n".join(summary)

# [V12.0] 공백 기간 동안의 흐름 요약 함수
def get_gap_analysis(ticker, last_date):
    gap_data = kis_chart.get_daily_chart(ticker)
    if not gap_data or not last_date: return "공백기 데이터 없음"
    
    clean_last_date = last_date.replace("-", "").replace(" ", "").replace(":", "")[:8]
    recent_moves = [d for d in gap_data if str(d['xymd']) > clean_last_date]
    
    if not recent_moves:
        return "마지막 분석 이후 특별한 주가 변동 없음."
    
    summary = f"마지막 분석({clean_last_date}) 이후 주가 흐름:\n"
    for d in recent_moves[:7]: # 최근 7일치 요약
        summary += f"- {d['xymd']}: 종가 ${d['clos']} ({d['rate']}%)\n"
    return summary

def get_strategy_report(ticker, chart_data_set, is_open, past_memories, news_data):
    daily_txt = summarize_data(chart_data_set['daily'], "Daily", 15)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly", 8)
    monthly_txt = summarize_data(chart_data_set['monthly'], "Monthly", 12)
    yearly_txt = summarize_data(chart_data_set['yearly'], "Recent 12 Months", 12)

    current_price = chart_data_set['current_price']
    volume_info = chart_data_set.get('volume_info', 'Volume: Data Unavailable')
    
    user_profile = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_profile, indent=2, ensure_ascii=False)

    # 공백기 분석 포함
    gap_summary = ""
    reflection_ctx = ""
    if past_memories:
        last_log_date = past_memories[0]['date']
        gap_summary = get_gap_analysis(ticker, last_log_date)
        
        reflection_ctx = "[Self-Correction: Past Performance Review]\n"
        for i, m in enumerate(past_memories):
            reflection_ctx += f"{i+1}. Date: {m['date']}, Price: ${m['price']}\n   Report Snippet: {m['report'][:200]}...\n"
    else:
        gap_summary = "이 종목에 대한 첫 번째 분석임."
        reflection_ctx = "[No past memories.]"

    status_msg = f"Market Status: {'OPEN' if is_open else 'CLOSED'}"
    
    # 가이드라인 (뉴스 및 캔들 패턴 분석 강화)
    guidelines = """
    1. Analyze Candlestick Patterns: Body/Tail size tells the real story.
    2. MA Disparity: Check if it's overbought/oversold.
    3. News Catalyst: Use provided news to explain 'Why' the price moves.
    4. Decisive Action: No vague talk. If it's bad, say it's bad.
    5. No disclaimers. Focus on data-driven conviction.
    """

    prompt = f"""
    Role: Senior Investment Strategist 'Mervis'.
    {status_msg} | Target: {ticker} (Current Price: ${current_price})
    {volume_info}
    
    [User Profile] {profile_str}
    [Background Resume: 공백기 흐름] {gap_summary}
    [Recent News] {news_data}
    [Technical Data] {yearly_txt} {monthly_txt} {weekly_txt} {daily_txt}
    {reflection_ctx}
    
    [Requirements]
    1. 말투: {USER_NAME}에게 똑똑하고 주관 뚜렷한 친구처럼 '반말'로 직설적으로 조언하라.
    2. 복기: 시작할 때 반드시 공백기 흐름과 지난 예측 성적을 언급하며 인사를 건네라.
    3. 분석: 캔들 패턴과 이격도를 기반으로 현재 시장의 에너지를 팩트 폭격하라.
    4. 확률: 과거 실수를 바탕으로 성공 확률을 냉정하게 제시하라.

    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Number only, $)
    목표가: (Number only, $)
    손절가: (Number only, $)
    기간: (e.g., 1 week)
    수익률: (e.g., 5%)
    확률: (e.g., 85%)
    코멘트: (Detailed analysis in Korean. Include '자기 복기 결과', '캔들 패턴 분석', '뉴스 결합 판단' 섹션을 포함할 것.)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: Error - {e}"

def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    latest_daily = d_data[0]
    if price == 0:
        p_val = latest_daily.get('clos') or latest_daily.get('last')
        if p_val: price = float(p_val)

    volume_info = f"Volume Data: (Last Close Volume: {latest_daily.get('acml_vol', 'N/A')})"

    chart_set = {
        'daily': d_data, 'weekly': w_data, 'monthly': m_data, 'yearly': y_data,
        'current_price': price, 'volume_info': volume_info
    }
    
    news_data = mervis_news.get_stock_news(ticker)
    is_open = kis_scan.is_market_open()
    past_memories = load_memories(ticker)
    
    report = get_strategy_report(ticker, chart_set, is_open, past_memories, news_data)
    
    if "전략:" in report:
        save_memory(ticker, price, report, news_data)
    
    return { "code": ticker, "price": price, "report": report }