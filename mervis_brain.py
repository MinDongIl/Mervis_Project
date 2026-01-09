from google import genai
import secret
import kis_chart
import kis_scan
import json
import re
import mervis_profile
import mervis_state 
import mervis_bigquery 
import mervis_painter

# 분석 모듈 임포트
from modules import technical, fundamental, supply

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

# --- 유틸리티 함수 ---

def load_memories(ticker):
    memories = mervis_bigquery.get_multi_memories(ticker, limit=3)
    return memories if memories else []

def extract_strategy_values(report_text):
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
        news_summary="News Disabled", 
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

# --- 리포트 생성 로직 ---

def get_strategy_report(ticker, chart_set, is_open, past_memories, analysis_results, feedback_list, user_profile, is_realtime=False):
    daily_txt = summarize_data(chart_set['daily'], "Daily", 15)
    weekly_txt = summarize_data(chart_set['weekly'], "Weekly", 8)
    current_price = chart_set['current_price']
    
    # 과거 기억 및 오답노트
    gap_summary = get_gap_analysis(ticker, past_memories[0]['date']) if past_memories else "First Analysis."
    reflection_ctx = ""
    if past_memories:
        reflection_ctx = "[Analysis History]\n" + "\n".join([f"{i+1}. {m['date']} Price:${m['price']} -> {m['report'][:100]}..." for i, m in enumerate(past_memories)])
    
    lessons_ctx = "[No specific past lessons.]"
    if feedback_list:
        lessons_ctx = "[YOUR PAST MISTAKES & LESSONS - DO NOT REPEAT!]\n" + "\n".join([f"- {f['date']} Result:{f['result']} | Lesson:{f['feedback']}" for f in feedback_list])

    # 데이터 추출
    tech_summary = analysis_results.get('tech_summary', 'N/A')
    
    # 펀더멘털 데이터 추출
    fund_data = analysis_results.get('fund_data', {})
    consensus = fund_data.get('consensus', {})
    valuation = fund_data.get('valuation', {})
    
    # 수급 데이터 추출
    supply_data = analysis_results.get('supply_data', {})
    supply_conclusion = analysis_results.get('supply_conclusion', 'N/A')

    # 투자 성향별 프롬프트
    style = user_profile.get('investment_style', 'SCALPING')
    style_instruction = ""
    
    if style == 'SCALPING':
        style_instruction = """
        [MODE: SCALPING (단타) on UPTREND]
        - **Philosophy**: "Only buy stocks with solid Future Earnings & Uptrend."
        - **Primary Indicators**: 
          1. **Trend**: Price MUST be above MA20/MA50.
          2. **Momentum**: Volume Spikes & VWAP Support.
          3. **Quality**: High Consensus Target Price (Future Earnings).
        - **Action**: Precise entry, tight stop-loss.
        - **Forbidden**: Do NOT mention 'News' or 'Rumors'. Focus on Data.
        """
    elif style == 'VALUE':
        style_instruction = """
        [MODE: VALUE INVESTING (가치투자)]
        - **Philosophy**: "Future Earnings (Consensus) is King."
        - **Primary Indicators**: Forward PE, Earnings Growth, Institutional Holdings.
        - **Secondary**: RSI for dip buying.
        - **Action**: Buy undervalued assets with growth potential.
        """
    else: # SWING
        style_instruction = """
        [MODE: SWING TRADING]
        - Focus on Trend (MA) and Future Performance.
        """

    # 실시간 데이터 여부에 따른 뉘앙스 추가
    time_ctx = "REAL-TIME LIVE DATA" if is_realtime else "Static Data (Market Closed or Delayed)"

    prompt = f"""
    You are 'Mervis', a professional AI Quant Trader customized for {USER_NAME}.
    Current Status: {'MARKET OPEN' if is_open else 'MARKET CLOSED'} | Data Source: {time_ctx}
    Ticker: {ticker} | **Current Price: ${current_price}**
    
    [User Profile] 
    {json.dumps(user_profile, indent=2, ensure_ascii=False)}
    
    {style_instruction}
    
    [1. Future Earnings & Fundamental (Most Important)]
    - Consensus Target: ${consensus.get('target_mean', 0)} (vs Current: ${current_price})
    - Recommendation: {consensus.get('recommendation', 'N/A').upper()}
    - Forward PE: {valuation.get('forward_pe', 0)} (Trailing PE: {valuation.get('trailing_pe', 0)})
    
    [2. Supply & Institutional Analysis]
    - Institutional Ownership: {supply_data.get('institution_pct', 0)*100:.1f}%
    - Short Ratio: {supply_data.get('short_ratio', 0)}
    - Hybrid Analysis Conclusion: **{supply_conclusion}**
    
    [3. Technical Facts (Chart & Trend)]
    {tech_summary}
    
    [Chart Data]
    {weekly_txt}
    {daily_txt}
    
    [Past Performance & Lessons]
    {gap_summary}
    {reflection_ctx}
    {lessons_ctx}
    
    [Instructions]
    1. **Style**: Speak to {USER_NAME} in Korean (반말). Be professional, cynical, and direct.
    2. **Anti-Hallucination**: **STOP generating immediately after your response. Do NOT simulate User interaction (e.g., "User: ...").**
    3. **Data Usage**: You MUST explicitly mention the [Consensus Target] and [Institutional Ownership] in your comment.
    
    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Specific Price, $)
    목표가: (Specific Price, $)
    손절가: (Specific Price, $)
    수익률: (%)
    확률: (%)
    
    코멘트:
    1. **미래 실적 및 펀더멘털**: (Analyze Consensus Target vs Current Price. Is it undervalued?)
    2. **수급 분석**: (Mention Institutional Ownership %. Is this a fake pump or real supply?)
    3. **차트 및 추세**: (Is it an uptrend? MA alignment?)
    4. **머비스의 판단**: (Final conclusion)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: API Error - {e}"

def analyze_stock(item):
    """
    종목 분석 메인 함수 (실시간 데이터 연동)
    """
    ticker = item['code']
    price = item.get('price', 0)
    
    # 1. 차트 데이터 로드 (Batch/Static)
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    latest_daily = d_data[0]
    volume_info = f"Vol: {latest_daily.get('acml_vol', 0)}"

    # 2. 실시간 데이터 확인 (Websocket State)
    # 웹소켓이 돌고 있고, 해당 종목이 감시 중이라면 최신가를 가져온다.
    realtime_data = mervis_state.get_realtime_data(ticker)
    is_realtime = False

    if realtime_data:
        price = realtime_data['price']
        change_rate = realtime_data.get('change', 0.0)
        rt_vol = realtime_data.get('volume', 0)
        volume_info = f"Live Vol: {rt_vol} ({change_rate}%)"
        is_realtime = True
        print(f" [Brain] {ticker} 실시간 데이터 적용: ${price}")
    else:
        # 실시간 데이터가 없으면 API 조회값이나 일봉 종가 사용
        if price == 0:
            p_val = latest_daily.get('clos') or latest_daily.get('last')
            if p_val: price = float(p_val)

    # 사용자 프로필 로드
    user_profile = mervis_profile.get_user_profile()
    style = user_profile.get('investment_style', 'SCALPING')

    # 성향별 전략 설정
    active_strategies = []
    if style == 'SCALPING':
        active_strategies = ['ma_cross', 'volume_spike', 'vwap']
    elif style == 'VALUE':
        active_strategies = ['rsi', 'bollinger'] 
    else: 
        active_strategies = ['ma_cross', 'rsi', 'vwap']

    # 3대 모듈 실행
    
    # 기술적 분석 (일봉 데이터 기준)
    tech_data, tech_err, tech_signals = technical.analyze_technical_signals(d_data, active_strategies)
    if tech_err: print(f" [Brain] Tech Warning: {tech_err}")

    # 수급 분석
    supply_data, supply_err, _ = supply.analyze_supply_structure(ticker)
    supply_conclusion = supply.analyze_hybrid_supply(supply_data, tech_signals)

    # 기본적 분석
    fund_data, fund_err, _ = fundamental.analyze_fundamentals(ticker)
    
    # 분석 결과 종합
    analysis_results = {
        'tech_summary': tech_data.get('summary', 'N/A') if tech_data else 'N/A',
        'fund_data': fund_data if fund_data else {},
        'supply_data': supply_data if supply_data else {},
        'supply_conclusion': supply_conclusion
    }
    
    chart_set = {
        'daily': d_data, 'weekly': w_data, 'monthly': m_data, 'yearly': y_data,
        'current_price': price, 'volume_info': volume_info
    }
    
    news_data = "" 
    is_open = kis_scan.is_market_open_check()
    past_memories = load_memories(ticker)
    
    feedback_list = []
    if hasattr(mervis_bigquery, 'get_past_lessons'):
        feedback_list = mervis_bigquery.get_past_lessons(ticker)
    
    # 차트 그리기
    chart_path = mervis_painter.draw_chart(ticker, d_data, highlight_indicators=tech_signals)
    if chart_path:
        print(f" [Painter] 차트 생성 완료 ({chart_path})")

    # 리포트 생성 (is_realtime 플래그 전달)
    report = get_strategy_report(ticker, chart_set, is_open, past_memories, analysis_results, feedback_list, user_profile, is_realtime=is_realtime)
    
    if "전략:" in report:
        save_memory(ticker, price, report, news_data)
    
    return { "code": ticker, "price": price, "report": report, "chart_path": chart_path }