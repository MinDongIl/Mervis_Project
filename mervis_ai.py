from google import genai
import secret
import mervis_profile 
import mervis_bigquery 
import mervis_brain
import json
import re

# Gemini 클라이언트 설정
client = genai.Client(api_key=secret.GEMINI_API_KEY)

def _get_recommendation_context(limit=3):
    """
    [핵심] 사용자가 '추천'을 원할 때, 
    AI가 상상하지 않고 DB에서 실제 점수가 높은 종목을 가져옴.
    """
    try:
        # DB에서 점수/거래량 기반 상위 종목 조회 (BigQuery 모듈에 이 함수가 있어야 함)
        # *만약 함수가 없다면 아래 get_top_ranked_stocks를 mervis_bigquery에 추가해야 함.
        # 여기서는 방어 코드로 작성.
        if hasattr(mervis_bigquery, 'get_top_ranked_stocks'):
            top_stocks = mervis_bigquery.get_top_ranked_stocks(limit)
        else:
            # 함수가 없으면 기존 리스트에서 최근 것만 가져옴 (임시 방편)
            top_stocks = mervis_bigquery.get_tickers_from_db(limit)

        if not top_stocks:
            return " [System] 현재 DB에 분석된 추천 유망 종목이 없습니다. '전체 스캔'을 먼저 수행하십시오."
            
        context = "[System Recommendation Data from DB]\n"
        for item in top_stocks:
            # 상세 분석 리포트 내용이 있다면 포함, 없으면 기본 정보
            report = item.get('report', '상세 분석 데이터 없음')
            code = item.get('code')
            score = item.get('total_score', 0)
            context += f"- 종목명: {code} | 점수: {score}점 | 분석요약: {report}\n"
        
        return context
    except Exception as e:
        return f" [System Error] 추천 데이터 조회 실패: {e}"

def start_consulting(initial_context=""):
    print("\n" + "="*40)
    print(" [MERVIS] Intelligent Chat Mode (Exit: q)")
    print("==================================================")
    
    # 1. 사용자 프로필 로드
    user_data = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_data, indent=2, ensure_ascii=False)
    
    # 2. 시스템 프롬프트 (성격 부여)
    system_instruction = f"""
    당신은 사용자의 냉철한 주식 비서 '머비스(Mervis)'입니다.
    
    [절대 원칙]
    1. 이모티콘을 절대 사용하지 마십시오.
    2. 말투: {USER_NAME}에게 똑똑하고 주관 뚜렷한 친구처럼 '반말'로 직설적으로 조언하라.
    3. [Context]에 없는 내용은 절대 지어내지 마십시오. 모르면 "데이터가 없습니다"라고 하십시오.
    4. "가상 종목 A" 같은 예시는 절대 들지 마십시오. 무조건 실존하는 티커(Ticker)만 언급하십시오.
    
    [User Profile]
    {profile_str}
    
    [Current System Context]
    {initial_context}
    """
    
    history = [] # 대화 기록 (Turn 관리)

    while True:
        try:
            user_input = input("\n>> User: ").strip()
        except KeyboardInterrupt:
            return "EXIT"

        if not user_input: continue
        if user_input.lower() in ['q', 'exit', 'quit']: return "EXIT"
        
        # 3. 사용자 의도 파악 (Intent Detection)
        
        # (A) 종목 분석 요청 감지 (티커 추출)
        # 영어 대문자 2~5글자 추출
        potential_tickers = re.findall(r'\b[A-Z]{2,5}\b', user_input.upper())
        # DB에 있는 티커인지 확인하거나, 명시적으로 "분석" 요청이 있는 경우
        found_tickers = []
        
        # (B) 추천 요청 감지
        recommend_keywords = ["추천", "종목 좀", "살만한거", "뭐 살까", "유망", "급등"]
        is_recommendation = any(k in user_input for k in recommend_keywords)

        # 4. 데이터 인출 (RAG)
        injected_context = ""

        # 4-1. 추천 요청인 경우 -> DB 랭킹 조회
        if is_recommendation:
            print(" [Mervis] DB 내 유망 종목 검색 중...", end="")
            rec_data = _get_recommendation_context(limit=3)
            injected_context += f"\n{rec_data}\n"
            print(" 완료.")

        # 4-2. 특정 종목 언급인 경우 -> Brain 분석 실행
        if potential_tickers:
            print(f" [Mervis] 데이터 분석: {potential_tickers}")
            for t in potential_tickers:
                # 뇌 가동 (실시간 API 조회 + DB 저장)
                res = mervis_brain.analyze_stock({'code': t, 'name': t, 'price': 0})
                if res:
                    injected_context += f"\n[Analysis Data for {t}]\n{res['report']}\n"
        
        # 5. 프롬프트 조립
        full_prompt = f"{system_instruction}\n"
        
        # 이전 대화 요약 (최근 2턴만 유지하여 토큰 절약)
        for h in history[-4:]: 
            full_prompt += f"{h}\n"
            
        full_prompt += f"\n[Injecting Real-time Data]\n{injected_context}\n"
        full_prompt += f"User: {user_input}\nMervis:"
        
        try:
            # 6. Gemini 응답 생성
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            answer = response.text.strip()
            print(f"Mervis: {answer}")
            
            # 대화 기록 저장
            history.append(f"User: {user_input}")
            history.append(f"Mervis: {answer}")
            
            # 사용자 성향 자동 업데이트 (백그라운드)
            if len(user_input) > 10:
                mervis_profile.update_user_profile(user_input)
                
        except Exception as e:
            print(f"[System Error] 응답 생성 실패: {e}")