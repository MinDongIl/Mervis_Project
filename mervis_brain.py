from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan
import json
import os
from datetime import datetime

# [머비스 두뇌 V9.2 - 일, 주, 월, 년 분석 통합]

client = genai.Client(api_key=secret.GEMINI_API_KEY)
MEMORY_FILE = "mervis_history.json"

# === 기억 장치 ===
def load_memory(ticker):
    if not os.path.exists(MEMORY_FILE): return None
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if ticker in data and data[ticker]: return data[ticker][-1]
    except: return None
    return None

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

# === 데이터 요약 함수 ===
def summarize_data(raw_data, period_name, limit=10):
    if not raw_data: return f"[{period_name}] 데이터 없음"
    
    df = pd.DataFrame(raw_data)
    try:
        cols = ['cymd', 'clos', 'rate']
        for c in cols: df[c] = pd.to_numeric(df[c])
    except: return f"[{period_name}] 데이터 오류"

    df = df.head(limit).iloc[::-1]
    
    summary = [f"[{period_name} Trend]"]
    for _, row in df.iterrows():
        summary.append(f"- {row['cymd']}: ${row['clos']} ({row['rate']}%)")
    
    return "\n".join(summary)

# === 메인 분석 로직 ===
def get_strategy_report(ticker, chart_data_set, is_open, past_memory):
    # 각 주기별 데이터 요약
    daily_txt = summarize_data(chart_data_set['daily'], "Daily(일)", 10)
    weekly_txt = summarize_data(chart_data_set['weekly'], "Weekly(주)", 8)
    monthly_txt = summarize_data(chart_data_set['monthly'], "Monthly(월)", 12)
    yearly_txt = summarize_data(chart_data_set['yearly'], "Yearly(년/장기)", 24)

    current_price = chart_data_set['current_price']
    
    # 기억 로드
    mem_ctx = ""
    if past_memory:
        mem_ctx = f"[과거 기록 ({past_memory['date']})]\n{past_memory['report']}\n\n[지시] 위 예측과 현재를 비교하여 평가하시오."
    else:
        mem_ctx = "[과거 기록 없음]"

    if is_open:
        status_msg = "현재 장은 '개장(Open)' 상태입니다."
        mission = """
        [미션: 실시간 전투 모드]
        현재 주가 흐름과 수급, 체결 강도를 분석하여 지금 당장 취해야 할 행동(진입/대기/청산)을 즉각적으로 판단하십시오.
        """
    else:
        status_msg = "현재 장은 '휴장(Closed)' 상태입니다."
        mission = """
        [미션: 전략 수립 모드]
        장기(월/년) 추세를 바탕으로 단기(일) 진입 시점을 설계하고, 내일 장 개장 시 유효한 시나리오를 설계하십시오.
        """

    # [복구된 20가지 상세 분석 지침]
    guidelines = """
    1. 추세가 상승세인지 하락세인지 파악하라.
    2. 변동성이 심한지 안정적인지 파악하라.
    3. 주요 지지선과 저항선을 식별하라.
    4. 거래량 변화 추이를 분석하라.
    5. 차트 패턴을 인식하라.
    6. 주요 뉴스 및 이벤트를 고려하라 (데이터 기반 추론).
    7. 시장의 전반적인 분위기를 파악하라.
    8. 투자자 심리를 분석하라.
    9. 유사 종목과의 비교 분석을 수행하라.
    10. 시장의 전반적인 트렌드를 파악하라.
    11. 투자자의 매수 및 매도 패턴을 분석하라.
    12. 유사 종목과의 상관관계를 분석하라.
    13. 시장의 전반적인 유동성을 파악하라.
    14. 주요 기관 투자자의 매매 동향을 분석하라.
    15. 글로벌 경제 지표와의 연관성을 분석하라.
    16. 기타 시장 참여자들의 행동을 분석하라.
    17. 시장의 전반적인 심리적 요인을 분석하라.
    18. 기술적 지표와의 연관성을 분석하라.
    19. 기타 요소들과의 상관관계를 분석하라.
    20. 주요 기술적 지표와의 연관성을 분석하라.
    """

    prompt = f"""
    당신은 민동일 님의 주식 선생님이자 냉철한 데이터 분석가 '머비스(Mervis)'입니다.
    {status_msg}
    
    대상 종목: {ticker} (현재가: ${current_price})

    [Timeframe Data (4단계 시계열)]
    1. {yearly_txt}
    2. {monthly_txt}
    3. {weekly_txt}
    4. {daily_txt}

    {mem_ctx}
    
    {mission}

    [상세 분석 지침 (필수 준수)]
    {guidelines}

    [분석 요구사항]
    1. 추세 분석: 장기(Year/Month)와 단기(Day) 추세를 종합하여 판단하라.
    2. 자가 평가: 과거 예측 대비 현재 상황 평가 (맞음/틀림/수정필요)
    3. 매매 전략:
       - 진입 추천가 (Buy Price)
       - 목표가 (Target Price)
       - 손절가 (Stop Loss)
    4. 예측 데이터:
       - 예상 보유 기간
       - 이 전략의 성공 확률 (Confidence, %)

    [출력 형식]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (숫자, $)
    목표가: (숫자, $)
    손절가: (숫자, $)
    기간: (예: 1주, 1달)
    수익률: (예: 5%)
    확률: (예: 70%)
    코멘트: (20가지 지침을 바탕으로 장단기 흐름을 꿰뚫는 핵심 요약)
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: {e}"

def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    # 4단계 데이터 수집
    d_data = kis_chart.get_daily_chart(ticker)
    w_data = kis_chart.get_weekly_chart(ticker)
    m_data = kis_chart.get_monthly_chart(ticker)
    y_data = kis_chart.get_yearly_chart(ticker)
    
    if not d_data: return None

    # 현재가 갱신
    if price == 0 and d_data:
        price = float(d_data[0]['clos'])

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