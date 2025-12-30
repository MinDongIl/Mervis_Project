from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan
import json
import os
from datetime import datetime

# [머비스 두뇌 V9.0 - 기억(Memory) & 자가 학습(Self-Learning) 탑재]
# 변경점: 분석 결과를 파일(DB)에 저장하고, 다음 분석 시 불러와서 비교/복기 수행

client = genai.Client(api_key=secret.GEMINI_API_KEY)
MEMORY_FILE = "mervis_history.json"

# === [기억 장치: DB 입출력] ===
def load_memory(ticker):
    """특정 종목의 과거 분석 기록(가장 최근 것)을 가져옵니다."""
    if not os.path.exists(MEMORY_FILE):
        return None
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 해당 종목의 기록이 있으면 가장 마지막(최근) 기록 반환
            if ticker in data and data[ticker]:
                return data[ticker][-1] 
    except:
        return None
    return None

def save_memory(ticker, report):
    """오늘의 분석 결과를 파일에 영구 저장합니다."""
    # 전략이 포함된 유의미한 리포트만 저장
    if "전략:" not in report:
        return

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = {"date": today, "report": report}
    
    data = {}
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}
    
    if ticker not in data:
        data[ticker] = []
    
    data[ticker].append(new_entry)
    
    # 최근 30개 (약 1.5개월 데이터 보존)
    if len(data[ticker]) > 30:
        data[ticker] = data[ticker][-30:]
        
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# === [AI 두뇌: 프롬프트 엔지니어링] ===
def get_strategy_report(ticker, chart_data, is_open, past_memory):
    # 최근 30일 데이터
    recent_data = chart_data.tail(30).to_string()
    current_price = chart_data['clos'].iloc[-1]
    
    # [1] 기억 소환 및 자가 검증 (핵심 기능)
    memory_context = ""
    if past_memory:
        memory_context = f"""
        [당신의 과거 분석 기록 (작성일: {past_memory['date']})]
        {past_memory['report']}
        
        [자가 학습 및 검증 지시]
        위 과거 기록에서 당신이 세운 전략과 현재 주가({current_price})를 비교하십시오.
        1. 당신의 예측(지지/저항/추세)이 적중했습니까?
        2. 예측이 빗나갔다면 그 원인은 무엇입니까? (뉴스, 수급, 판단 미스 등)
        3. 과거의 판단을 맹신하지 말고, 피드백을 반영하여 오늘의 전략을 수정하십시오.
        """
    else:
        memory_context = "[신규 종목] 이 종목에 대한 과거 분석 데이터가 없습니다. 제로베이스에서 분석을 시작하십시오."

    # [2] 상황별 미션 설정
    if is_open:
        status_msg = "현재 장은 '개장(Open)' 상태입니다."
        mission = """
        [미션: 실시간 대응 및 검증]
        과거의 전략이 현재 시장에서 유효한지 즉시 검증하고, 호가와 체결 강도를 고려해 진입/청산 여부를 결정하십시오.
        """
    else:
        status_msg = "현재 장은 '휴장(Closed)' 상태입니다."
        mission = """
        [미션: 복기 및 전략 수립]
        직전 장의 마감 데이터를 분석하여 당신의 지난 예측을 평가(Feedback)하고, 내일 장을 위한 정밀 시나리오를 설계하십시오.
        """

    # [3] 20가지 상세 분석 지침
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

    # [4] 최종 프롬프트 조립
    prompt = f"""
    당신은 민동일 님의 주식 파트너이자 데이터를 끊임없이 학습하는 AI '머비스(Mervis)'입니다.
    {status_msg}
    
    대상 종목: {ticker}
    
    [데이터]
    {recent_data}
    
    {memory_context}
    
    {mission}
    
    [상세 분석 지침]
    {guidelines}

    [분석 요구사항]
    1. 추세 분석: 현재 상승세인가, 하락세인가, 박스권인가?
    2. 자가 평가: 과거 예측 대비 현재 상황 평가 (맞음/틀림/수정필요)
    3. 매매 전략:
       - 진입 추천가 (Buy Price)
       - 목표가 (Target Price)
       - 손절가 (Stop Loss)
    4. 예측 데이터:
       - 예상 보유 기간
       - 이 전략의 성공 확률 (Confidence, %)
       
    [출력 형식 - 파싱을 위해 정확히 지킬 것]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (숫자만, $)
    목표가: (숫자만, $)
    손절가: (숫자만, $)
    기간: (예: 1주, 1달)
    수익률: (예: 5%)
    확률: (예: 70%)
    코멘트: (과거 예측에 대한 피드백 포함, 핵심 근거 한 줄 요약)
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"전략: 분석불가\n코멘트: API 통신 오류 ({e})"

def analyze_stock(item):
    ticker = item['code']
    price = item.get('price', 0)
    
    # 1. 차트 데이터 확보
    raw_data = kis_chart.get_daily_price(ticker)
    if not raw_data: return None
    
    # 2. 데이터 가공
    df = pd.DataFrame(raw_data)
    if 'acml_vol' in df.columns: 
        df.rename(columns={'acml_vol': 'vol'}, inplace=True)
    
    cols = ['clos', 'open', 'high', 'low']
    if 'vol' in df.columns: cols.append('vol')
        
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    df = df.iloc[::-1].reset_index(drop=True)
    
    if price == 0 and not df.empty:
        price = df['clos'].iloc[-1]
    
    # 3. 시장 상태 확인
    is_open = kis_scan.is_market_open()
    
    # [핵심] 4. 과거 기억 로드
    past_memory = load_memory(ticker)
    
    # 5. AI 분석 (과거 기억 주입)
    report = get_strategy_report(ticker, df, is_open, past_memory)
    
    # 6. 새로운 기억 저장 (학습)
    save_memory(ticker, report)
    
    return {
        "code": ticker,
        "price": price,
        "report": report
    }