from google import genai
import secret
import kis_chart
import kis_scan
import json
import re
import mervis_profile
import mervis_state 
import mervis_news 
import mervis_bigquery 
import mervis_painter

# 분리된 기술적 분석 모듈 임포트
from modules import technical

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

# --- 유틸리티 함수 (메모리, 데이터 요약 등) ---

def load_memories(ticker):
    memories = mervis_bigquery.get_multi_memories(ticker, limit=3)
    return memories if memories else []

def extract_strategy_values(report_text):
    """Gemini 리포트에서 전략, 목표가, 손절가 추출"""
    try:
        data = {"action": "HOLD", "target_price": 0.0, "cut_price": 0.0}
        if "매수추천" in report_text or "매수 권고" in report_text: 
            data["action"] = "BUY"
        elif "매도권고" in report_text: 
            data["action"] = "SELL"
        
        t_match = re.search(r"목표가[:\s\$]+([\d\.]+)", report_text)
        if t_match: data["target_price"] = float(t_match.group(1))
        
        c_match = re.search(r"손절가[:\s\$]+([\d\.]+)", report_text)
        if c_match: data["cut_price"] = float(c_match.group(1))
        
        return data
    except:
        return {"action": "HOLD", "target_price": 0.0, "cut_price": 0.0}

def save_memory(ticker, price, report, news_data):
    if "전략:" not in report: return
    mode = mervis_state.get_mode()
    strategy_data = extract_strategy_values(report)
    
    mervis_bigquery.save_log(
        ticker=ticker, 
        mode=mode, 
        price=price,
        report=report, 
        news_summary=news_data,
        action=strategy_data['action'],
        target_price=strategy_data['target_price'],
        cut_price=strategy_data['cut_price']
    )

def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data available."
    import pandas as pd
    df = pd.DataFrame(raw_data)
    if 'xymd' in df.columns: df.rename(columns={'xymd': 'cymd'}, inplace=True)
    try:
        cols = ['clos', 'open', 'high', 'low']
        for c in cols: 
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
        df['cymd'] = df['cymd'].astype(str)
    except: return f"[{period_name}] Parsing Error"
    
    df = df.head(limit).iloc[::-1]
    summary = [f"[{period_name} Candlestick]"]
    for _, row in df.iterrows():
        summary.append(f"Date:{row['cymd']} O:${row['open']} H:${row['high']} L:${row['low']} C:${row['clos']}")
    return "\n".join(summary)

def get_gap_analysis(ticker, last_date):
    gap_data = kis_chart.get_daily_chart(ticker)
    if not gap_data or not last_date: return "공백기 데이터 없음"
    clean_last = last_date.replace("-", "").replace(" ", "").replace(":", "")[:8]
    recent = [d for d in gap_data if str(d['xymd']) > clean_last]
    if not recent: return "마지막 분석 이후 변동 없음."
    summary = f"마지막 분석({clean_last}) 이후 흐름:\n"
    for d in recent[:5]:
        summary += f"- {d['xymd']}: ${d['clos']} ({d['rate']}%)\n"
    return summary

# --- 리포트 생성 로직 (Control Tower) ---

def get_strategy_report(ticker, chart_set, is_open, past_memories, news_data, tech_summary, feedback_list, user_profile):
    daily_txt = summarize_data(chart_set['daily'], "Daily", 15)
    weekly_txt = summarize_data(chart_set['weekly'], "Weekly", 8)
    current_price = chart_set['current_price']
    
    # 과거 기억 및 오답노트 컨텍스트
    gap_summary = get_gap_analysis(ticker, past_memories[0]['date']) if past_memories else "First Analysis."
    reflection_ctx = ""
    if past_memories:
        reflection_ctx = "[Analysis History]\n" + "\n".join([f"{i+1}. {m['date']} Price:${m['price']} -> {m['report'][:100]}..." for i, m in enumerate(past_memories)])
    
    lessons_ctx = "[No specific past lessons.]"
    if feedback_list:
        lessons_ctx = "[YOUR PAST MISTAKES & LESSONS - DO NOT REPEAT!]\n" + "\n".join([f"- {f['date']} Result:{f['result']} | Lesson:{f['feedback']}" for f in feedback_list])

    # 투자 성향에 따른 프롬프트 지침 변경
    style = user_profile.get('investment_style', 'SCALPING')
    style_instruction = ""
    
    if style == 'SCALPING':
        style_instruction = """
        [MODE: SCALPING (단타)]
        - **Core Indicators**: Volume Spikes, VWAP, 5-day/20-day MA Cross.
        - **Action**: Look for immediate momentum. Entry must be precise.
        - **Stop-Loss**: Very tight (within 2-3%).
        - Ignore long-term valuation; focus on price action and flow.
        """
    elif style == 'VALUE':
        style_instruction = """
        [MODE: VALUE INVESTING (가치투자)]
        - **Core Indicators**: RSI (for dip buying), Sector Trends, Fundamentals.
        - **Action**: Look for undervalued assets or solid uptrends.
        - **Stop-Loss**: Wider range allowed to withstand volatility.
        - Ignore short-term noise; focus on medium/long-term potential.
        """
    else: # SWING
        style_instruction = """
        [MODE: SWING TRADING (스윙)]
        - **Core Indicators**: MA50 Support, MACD Reversal, RSI Divergence.
        - **Action**: Capture trend reversals or continuations over days/weeks.
        """

    prompt = f"""
    You are 'Mervis', a professional AI Quant Trader customized for {USER_NAME}.
    Current Status: {'MARKET OPEN' if is_open else 'MARKET CLOSED'} | Ticker: {ticker} | Price: ${current_price}
    
    [User Profile] 
    {json.dumps(user_profile, indent=2, ensure_ascii=False)}
    
    {style_instruction}
    
    [Hard Mathematical Facts (From Modules)]
    {tech_summary}
    
    [Recent News] 
    {news_data}
    
    [Chart Data]
    {weekly_txt}
    {daily_txt}
    
    [Past Performance]
    {gap_summary}
    {reflection_ctx}
    
    {lessons_ctx}
    
    [Instructions]
    1. **Style**: Speak to {USER_NAME} in Korean (반말). Be professional, cynical, and direct.
    2. **Analysis**: Strictly follow the [MODE] instructions above.
    3. **Self-Correction**: Review [YOUR PAST MISTAKES]. If a similar pattern appears, warn the user.
    
    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Specific Price, $)
    목표가: (Specific Price, $)
    손절가: (Specific Price, $)
    수익률: (Expected %)
    확률: (Win Rate %)
    
    코멘트:
    1. **기술적 분석**: (Explain based on the specific indicators for the current MODE)
    2. **재료/뉴스**: (Impact on price)
    3. **과거 경험 적용**: (Did you apply any lessons?)
    4. **머비스의 판단**: (Final conclusion)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: API Error - {e}"

def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    # 차트 데이터 수집
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    latest_daily = d_data[0]
    if price == 0:
        p_val = latest_daily.get('clos') or latest_daily.get('last')
        if p_val: price = float(p_val)

    # 1. 사용자 프로필 로드
    user_profile = mervis_profile.get_user_profile()
    style = user_profile.get('investment_style', 'SCALPING')

    # 2. 성향에 따른 활성 전략 선택
    active_strategies = []
    if style == 'SCALPING':
        active_strategies = ['ma_cross', 'volume_spike', 'vwap']
    elif style == 'VALUE':
        active_strategies = ['rsi', 'bollinger'] 
    else: # SWING
        active_strategies = ['ma_cross', 'rsi', 'vwap']

    # 3. 모듈형 기술적 분석 수행
    # technical 모듈을 호출하여 필요한 지표만 계산하고 신호(signals)를 받음
    tech_data, tech_err, signals = technical.analyze_technical_signals(d_data, active_strategies)
    
    if tech_err: print(f" [Brain] Tech Warning: {tech_err}")

    volume_info = f"Volume: {latest_daily.get('acml_vol', 'N/A')}"
    chart_set = {
        'daily': d_data, 'weekly': w_data, 'monthly': m_data, 'yearly': y_data,
        'current_price': price, 'volume_info': volume_info
    }
    
    news_data = mervis_news.get_stock_news(ticker)
    is_open = kis_scan.is_market_open_check()
    past_memories = load_memories(ticker)
    
    # 오답노트 로드
    feedback_list = []
    if hasattr(mervis_bigquery, 'get_past_lessons'):
        feedback_list = mervis_bigquery.get_past_lessons(ticker)
    
    # 4. 차트 그리기 (분석된 신호를 하이라이팅)
    chart_path = mervis_painter.draw_chart(ticker, d_data, highlight_indicators=signals)
    if chart_path:
        print(f" [Painter] 차트 생성 완료 ({chart_path})")

    # 5. 최종 리포트 생성 (tech_data['summary']는 모듈에서 만들어준 요약 텍스트)
    tech_summary = tech_data.get('summary', 'N/A') if tech_data else 'N/A'
    report = get_strategy_report(ticker, chart_set, is_open, past_memories, news_data, tech_summary, feedback_list, user_profile)
    
    # 결과 저장
    if "전략:" in report:
        save_memory(ticker, price, report, news_data)
    
    return { "code": ticker, "price": price, "report": report, "chart_path": chart_path }