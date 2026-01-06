from google import genai
import secret
import kis_chart
import pandas as pd
import pandas_ta as ta
import kis_scan
import json
import os
import re
from datetime import datetime
import mervis_profile
import mervis_state 
import mervis_news 
import mervis_bigquery 

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

# 기술적 지표 계산 함수 (기존 동일)
def calculate_technical_indicators(daily_data):
    try:
        if not daily_data: return None, "데이터 부족"
        df = pd.DataFrame(daily_data)
        df = df.rename(columns={'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'})
        cols = ['close', 'open', 'high', 'low', 'volume']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.sort_values('date').reset_index(drop=True)
        if len(df) < 50: return None, "데이터 50일 미만"

        df['MA50'] = ta.sma(df['close'], length=50)
        df['MA20'] = ta.sma(df['close'], length=20)
        df['RSI'] = ta.rsi(df['close'], length=14)
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        bb = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bb], axis=1)

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        close = curr['close']
        ma50 = curr['MA50']
        rsi = curr['RSI']
        
        macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
        signal_col = [c for c in df.columns if c.startswith('MACDs_')][0]
        macd_val = curr[macd_col]
        signal_val = curr[signal_col]
        prev_macd = prev[macd_col]
        prev_signal = prev[signal_col]

        signals = []
        trend = "상승추세(Bullish)" if close > ma50 else "하락추세(Bearish)"
        
        if rsi <= 30: signals.append("RSI 과매도(침체권) - 기술적 반등 가능성 높음")
        elif rsi >= 70: signals.append("RSI 과매수(과열권) - 조정 가능성 주의")
        else: signals.append(f"RSI 중립 ({rsi:.1f})")
        
        if macd_val > signal_val:
            if prev_macd <= prev_signal: signals.append("MACD 골든크로스 발생 (매수 신호)")
            else: signals.append("MACD 매수 우위 유지")
        else:
            if prev_macd >= prev_signal: signals.append("MACD 데드크로스 발생 (매도 신호)")
            else: signals.append("MACD 매도 우위 유지")
            
        disparity = (close / curr['MA20']) * 100
        
        tech_summary = f"""
        [Hard Math Indicators]
        - Current Price: ${close}
        - Trend(MA50): {trend} (Price vs MA50: ${ma50:.2f})
        - RSI(14): {rsi:.2f} ({'Oversold' if rsi<=30 else 'Overbought' if rsi>=70 else 'Neutral'})
        - MACD: {macd_val:.2f} / Signal: {signal_val:.2f}
        - Disparity(MA20): {disparity:.2f}%
        - Key Signals: {', '.join(signals)}
        """
        return {
            "rsi": rsi, "ma50": ma50, "macd": macd_val, "signals": signals, "summary": tech_summary
        }, None
    except Exception as e:
        return None, f"지표 계산 오류: {e}"

def load_memories(ticker):
    memories = mervis_bigquery.get_multi_memories(ticker, limit=3)
    return memories if memories else []

# [수정] 정규표현식으로 리포트에서 숫자 추출
def extract_strategy_values(report_text):
    """
    Gemini 리포트에서 전략, 목표가, 손절가 추출
    Format: "목표가: $150.0" -> 150.0
    """
    try:
        data = {
            "action": "HOLD", # 기본값
            "target_price": 0.0,
            "cut_price": 0.0
        }
        
        # 1. 전략 추출 (매수/매도/관망)
        if "매수추천" in report_text or "매수 권고" in report_text:
            data["action"] = "BUY"
        elif "매도권고" in report_text:
            data["action"] = "SELL"
        
        # 2. 목표가 추출 (예: 목표가: 150.5, 목표가: $150)
        # 정규식: "목표가" 뒤에 오는 숫자(소수점 포함) 추출
        target_match = re.search(r"목표가[:\s\$]+([\d\.]+)", report_text)
        if target_match:
            data["target_price"] = float(target_match.group(1))
            
        # 3. 손절가 추출
        cut_match = re.search(r"손절가[:\s\$]+([\d\.]+)", report_text)
        if cut_match:
            data["cut_price"] = float(cut_match.group(1))
            
        return data
    except:
        return {"action": "HOLD", "target_price": 0.0, "cut_price": 0.0}

def save_memory(ticker, price, report, news_data):
    if "전략:" not in report: return
    mode = mervis_state.get_mode()
    
    # [추가] 리포트에서 전략 수치 추출
    strategy_data = extract_strategy_values(report)
    
    # [수정] current_price -> price 로 변경
    mervis_bigquery.save_log(
        ticker=ticker, 
        mode=mode, 
        price=price,
        report=report, 
        news_summary=news_data,
        # [신규 인자] 예측 데이터
        action=strategy_data['action'],
        target_price=strategy_data['target_price'],
        cut_price=strategy_data['cut_price']
    )

def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] No Data available."
    df = pd.DataFrame(raw_data)
    if 'xymd' in df.columns: df.rename(columns={'xymd': 'cymd'}, inplace=True)
    try:
        cols = ['clos', 'open', 'high', 'low']
        for c in cols: 
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
        df['cymd'] = df['cymd'].astype(str)
    except: return f"[{period_name}] Data Parsing Error"
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

def get_strategy_report(ticker, chart_data_set, is_open, past_memories, news_data, tech_data):
    daily_txt = summarize_data(chart_data_set['daily'], "Daily", 15)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly", 8)
    current_price = chart_data_set['current_price']
    
    user_profile = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_profile, indent=2, ensure_ascii=False)

    gap_summary = ""
    reflection_ctx = ""
    if past_memories:
        last_log_date = past_memories[0]['date']
        gap_summary = get_gap_analysis(ticker, last_log_date)
        reflection_ctx = "[Self-Correction: Past Performance]\n"
        for i, m in enumerate(past_memories):
            reflection_ctx += f"{i+1}. {m['date']} Price:${m['price']} -> Report: {m['report'][:150]}...\n"
    else:
        gap_summary = "First Analysis."
        reflection_ctx = "[No past memories.]"

    tech_injection = tech_data['summary'] if tech_data else "[Technical Error] Calculation Failed."

    prompt = f"""
    You are 'Mervis', a highly capable AI Quant Trader.
    Current Status: {'MARKET OPEN' if is_open else 'MARKET CLOSED'} | Ticker: {ticker} | Price: ${current_price}
    
    [User Profile] 
    {profile_str}
    
    [Hard Mathematical Facts - DO NOT HALLUCINATE]
    {tech_injection}
    
    [Recent News] 
    {news_data}
    
    [Chart Data]
    {weekly_txt}
    {daily_txt}
    
    [Reflection]
    {gap_summary}
    {reflection_ctx}
    
    [Instructions]
    1. **Style**: Speak to {USER_NAME} like a professional hedge fund manager. Use straight talk (반말). Be cynical but accurate.
    2. **Strategy**: Use the 'Hard Mathematical Facts' (RSI, MACD, MA50) as your primary evidence.
       - If RSI < 30, emphasize "Oversold opportunity".
       - If MACD Golden Cross, emphasize "Trend Reversal".
       - If Price < MA50, warn about "Downtrend".
    3. **Consistency**: Check your [Reflection]. If you were wrong before, admit it and adjust.
    
    [Output Format]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (Specific Price, $)
    목표가: (Specific Price, $)
    손절가: (Specific Price, $)
    수익률: (Expected %)
    확률: (Win Rate %)
    
    코멘트:
    1. **기술적 팩트 체크**: (Mention RSI, MACD, MA50 explicitly based on provided data)
    2. **뉴스/재료 분석**: (Connect news to price movement)
    3. **머비스의 판단**: (Final conclusion)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: API Error - {e}"

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

    tech_data, tech_err = calculate_technical_indicators(d_data)
    if not tech_data: print(f" [Brain] Tech Calculation Warning: {tech_err}")

    volume_info = f"Volume: {latest_daily.get('acml_vol', 'N/A')}"
    chart_set = {
        'daily': d_data, 'weekly': w_data, 'monthly': m_data, 'yearly': y_data,
        'current_price': price, 'volume_info': volume_info
    }
    
    news_data = mervis_news.get_stock_news(ticker)
    is_open = kis_scan.is_market_open_check()
    past_memories = load_memories(ticker)
    
    report = get_strategy_report(ticker, chart_set, is_open, past_memories, news_data, tech_data)
    
    if "전략:" in report:
        save_memory(ticker, price, report, news_data)
    
    return { "code": ticker, "price": price, "report": report }