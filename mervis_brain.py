from google import genai
import secret
import kis_chart
import pandas as pd
import kis_scan

# [머비스 두뇌 V8.0 - 정밀 분석 & 동적 미션]
client = genai.Client(api_key=secret.GEMINI_API_KEY)

def get_strategy_report(ticker, chart_data, is_open):
    # 최근 30일 데이터 (텍스트화)
    recent_data = chart_data.tail(30).to_string()
    
    # [1] 상황별 미션 설정 (동적 변경)
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
        직전 장의 데이터를 정밀 복기하고 과거 패턴을 분석하여, 다음 장 개장 시 유효한 진입/청산 시나리오를 미리 설계하십시오.
        """

    # [2] 20가지 상세 분석 지침 (요청하신 내용 반영)
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

    # [3] 최종 프롬프트 조립
    prompt = f"""
    당신은 민동일 님의 주식 선생님이자 냉철한 데이터 분석가 '머비스(Mervis)'입니다.
    {status_msg}
    
    대상 종목: {ticker}
    
    [데이터]
    {recent_data}
    
    {mission}
    
    [상세 분석 지침]
    {guidelines}

    [분석 요구사항]
    1. 추세 분석: 현재 상승세인가, 하락세인가, 박스권인가?
    2. 매매 전략:
       - 진입 추천가 (Buy Price): 지지선을 고려한 안전한 가격
       - 목표가 (Target Price): 저항선을 고려한 1차 익절 가격
       - 손절가 (Stop Loss): 추세가 무너지는 가격
    3. 예측 데이터:
       - 예상 보유 기간 (단기/중기)
       - 예상 수익률 (%)
       - 이 전략의 성공 확률 (Confidence, %)
       
    [출력 형식 - 파싱을 위해 정확히 지킬 것]
    전략: (매수추천 / 관망 / 매도권고 / 매수대기)
    진입가: (숫자만, $)
    목표가: (숫자만, $)
    손절가: (숫자만, $)
    기간: (예: 1주, 1달)
    수익률: (예: 5%)
    확률: (예: 70%)
    코멘트: (분석 내용 한 줄 요약)
    """
    
    try:
        # 유료 플랜이므로 지연 없이 즉시 호출
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
    
    # 1. 차트 데이터 확보 (실전 서버)
    raw_data = kis_chart.get_daily_price(ticker)
    if not raw_data: return None
    
    # 2. 데이터 가공
    df = pd.DataFrame(raw_data)
    # 필드명 호환성 처리
    if 'acml_vol' in df.columns: 
        df.rename(columns={'acml_vol': 'vol'}, inplace=True)
    
    # 숫자 변환
    cols = ['clos', 'open', 'high', 'low']
    if 'vol' in df.columns: cols.append('vol')
        
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    df = df.iloc[::-1].reset_index(drop=True)
    
    # 현재가가 0이면 차트 종가로 대체
    if price == 0 and not df.empty:
        price = df['clos'].iloc[-1]
    
    # 3. 시장 상태 확인 (동적 판별)
    is_open = kis_scan.is_market_open()
    
    # 4. AI 분석 (동적 미션 적용)
    report = get_strategy_report(ticker, df, is_open)
    
    return {
        "code": ticker,
        "price": price,
        "report": report
    }