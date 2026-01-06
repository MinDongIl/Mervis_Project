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
import mervis_painter

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

# 기술적 지표 계산 함수
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

def extract_strategy_values(report_text):
    """
    Gemini 리포트에서 전략, 목표가, 손절가 추출
    """
    try:
        data = {
            "action": "HOLD",
            "target_price": 0.0,
            "cut_price": 0.0
        }
        if "매수추천" in report_text or "매수 권고" in report_text:
            data["action"] = "BUY"
        elif "매도권고" in report_text:
            data["action"] = "SELL"
        
        target_match = re.search(r"목표가[:\s\$]+([\d\.]+)", report_text)
        if target_match:
            data["target_price"] = float(target_match.group(1))
            
        cut_match = re.search(r"손절가[:\s\$]+([\d\.]+)", report_text)
        if cut_match:
            data["cut_price"] = float(cut_match.group(1))
            
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

# [수정] feedback_list 인자 추가
def get_strategy_report(ticker, chart_data_set, is_open, past_memories, news_data, tech_data, feedback_list):
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
        reflection_ctx = "[Analysis History]\n"
        for i, m in enumerate(past_memories):
            reflection_ctx += f"{i+1}. {m['date']} Price:${m['price']} -> Report: {m['report'][:150]}...\n"
    else:
        gap_summary = "First Analysis."
        reflection_ctx = "[No past memories.]"

    # [신규] 과거 교훈(오답노트) 컨텍스트 생성
    lessons_ctx = ""
    if feedback_list:
        lessons_ctx = "[YOUR PAST MISTAKES & LESSONS - DO NOT REPEAT!]\n"
        for f in feedback_list:
            lessons_ctx += f"- Date: {f['date']} | Result: {f['result']} | Lesson: {f['feedback']}\n"
    else:
        lessons_ctx = "[No specific past lessons found.]"

    tech_injection = tech_data['summary'] if tech_data else "[Technical Error] Calculation Failed."

    prompt = f"""
    You are 'Mervis', a highly capable AI Quant Trader.
    Current Status: {'MARKET OPEN' if is_open else 'MARKET CLOSED'} | Ticker: {ticker} | Price: ${current_price}
    
    [User Profile] 
    {profile_str}
    
    [Hard Mathematical Facts]
    {tech_injection}
    
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
    1. **Style**: Speak to {USER_NAME} like a professional hedge fund manager. Use straight talk (반말). Be cynical but accurate.
    2. **Strategy**: Use the 'Hard Mathematical Facts' (RSI, MACD, MA50) as your primary evidence.
       - If RSI < 30, emphasize "Oversold opportunity".
       - If MACD Golden Cross, emphasize "Trend Reversal".
       - If Price < MA50, warn about "Downtrend".
    3. **Self-Correction**: STRICTLY review [YOUR PAST MISTAKES & LESSONS]. If you failed before with a similar pattern, acknowledge it and adjust your strategy.
    
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
    3. **과거 경험 적용**: (Mention if any lesson was applied from 'Past Mistakes')
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
    
    # [신규] DB에서 과거 오답노트 조회
    feedback_list = []
    if hasattr(mervis_bigquery, 'get_past_lessons'):
        feedback_list = mervis_bigquery.get_past_lessons(ticker)
    
    # 리포트 생성 시 feedback_list 전달
    report = get_strategy_report(ticker, chart_set, is_open, past_memories, news_data, tech_data, feedback_list)
    
    if "전략:" in report:
        save_memory(ticker, price, report, news_data)
    
    return { "code": ticker, "price": price, "report": report }

def calculate_technical_indicators(daily_data):
    try:
        if not daily_data: return None, "데이터 부족", []
        
        df = pd.DataFrame(daily_data)
        df = df.rename(columns={'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'})
        cols = ['close', 'open', 'high', 'low', 'volume']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.sort_values('date').reset_index(drop=True)
        
        if len(df) < 60: return None, "데이터 부족 (최소 60일)", []

        # --- 1. 모든 지표 계산 ---
        df['MA50'] = ta.sma(df['close'], length=50)
        df['MA20'] = ta.sma(df['close'], length=20)
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        # MACD
        macd = ta.macd(df['close'])
        df = pd.concat([df, macd], axis=1)
        
        # Bollinger Bands
        bb = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bb], axis=1)
        
        # Ichimoku (일목균형표)
        ichimoku_df, _ = ta.ichimoku(df['high'], df['low'], df['close'])
        df = pd.concat([df, ichimoku_df], axis=1)

        # --- 2. 핵심 근거(Key Factors) 선정 로직 ---
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        key_factors = [] 

        # A. [50일선 추세 전략]
        # 가격이 50일선 근처에서 지지를 받거나 돌파할 때
        if abs(curr['close'] - curr['MA50']) / curr['MA50'] < 0.02: # 2% 이내 근접
            key_factors.append('MA50') # 추세선 지지 테스트 중

        # B. [RSI 전략]
        if curr['RSI'] <= 35 or curr['RSI'] >= 65:
            key_factors.append('RSI')
            
        # C. [일목균형표 전략]
        # 구름대(Span A, Span B) 위에 있는지 확인 (pandas_ta 컬럼명이 ISA_..., ISB_... 형태)
        span_a_col = [c for c in df.columns if c.startswith('ISA_')][0]
        span_b_col = [c for c in df.columns if c.startswith('ISB_')][0]
        
        span_a = curr[span_a_col]
        span_b = curr[span_b_col]
        
        # 구름대 돌파 직후거나, 구름대 지지 중일 때
        if curr['close'] > max(span_a, span_b):
            # 전날엔 구름대 아래였다면 -> 돌파 (강력 매수)
            if prev['close'] <= max(prev[span_a_col], prev[span_b_col]):
                key_factors.append('Ichimoku')

        # D. [MACD 전략]
        macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
        signal_col = [c for c in df.columns if c.startswith('MACDs_')][0]
        if abs(curr[macd_col] - curr[signal_col]) < 0.5:
             key_factors.append('MACD')

        # E. [볼린저밴드 전략]
        bbu_col = [c for c in df.columns if c.startswith('BBU_')][0]
        bbl_col = [c for c in df.columns if c.startswith('BBL_')][0]
        if curr['close'] >= curr[bbu_col] * 0.99 or curr['close'] <= curr[bbl_col] * 1.01:
            key_factors.append('Bollinger')

        # 요약 텍스트 생성 (기존 유지)
        tech_summary = f"""
        [Technical Indicators]
        Price: {curr['close']} | MA50: {curr['MA50']:.2f} | RSI: {curr['RSI']:.2f}
        Cloud Top: {max(span_a, span_b):.2f} (Price is {'Above' if curr['close'] > max(span_a, span_b) else 'Below'} Cloud)
        """

        return {
            "rsi": curr['RSI'], "ma50": curr['MA50'], "summary": tech_summary
        }, None, key_factors 

    except Exception as e:
        return None, f"지표 오류: {e}", []