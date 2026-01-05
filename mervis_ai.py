from google import genai
import secret
import mervis_profile 
import mervis_bigquery 
import mervis_brain
import kis_websocket  # [추가] 알림 설정 연동
import json
import re

# Gemini 클라이언트 설정
client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_NAME = getattr(secret, 'USER_NAME', '사용자')

def _get_recommendation_context(limit=3):
    """
    [핵심] 사용자가 '추천'을 원할 때 DB 데이터 조회
    """
    try:
        if hasattr(mervis_bigquery, 'get_top_ranked_stocks'):
            top_stocks = mervis_bigquery.get_top_ranked_stocks(limit)
        else:
            top_stocks = mervis_bigquery.get_tickers_from_db(limit)

        if not top_stocks:
            return " [System] 현재 DB에 분석된 추천 유망 종목이 없습니다."
            
        context = "[System Recommendation Data from DB]\n"
        for item in top_stocks:
            report = item.get('report', '상세 분석 데이터 없음')
            code = item.get('code')
            score = item.get('total_score', 0)
            context += f"- 종목명: {code} | 점수: {score}점 | 분석요약: {report}\n"
        
        return context
    except Exception as e:
        return f" [System Error] 추천 데이터 조회 실패: {e}"

def _extract_alert_params(user_input):
    """
    [신규] 사용자의 자연어 명령에서 알림 설정에 필요한 정보(티커, 가격, 조건)를 추출
    """
    try:
        # 추출 전용 프롬프트
        prompt = f"""
        Extract stock alert parameters from the text below.
        Return ONLY a JSON object with keys: "ticker" (US symbol, e.g., TSLA), "price" (number), "condition" ("GE" for >=, "LE" for <=).
        If the user implies "rising to" or "breaking", use "GE". If "dropping to", use "LE".
        If no specific price is mentioned, return null.
        
        Text: "{user_input}"
        JSON:
        """
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        # JSON 파싱
        text = response.text.strip()
        # 마크다운 코드블록 제거
        if "```" in text:
            text = text.replace("```json", "").replace("```", "")
        
        data = json.loads(text)
        
        # 필수 값 체크
        if data and data.get('ticker') and data.get('price'):
            return data
        return None
    except:
        return None

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
    4. 사용자가 "알림"이나 "감시"를 요청하면, 시스템이 이미 설정을 완료했음을 인지하고 확인해 주십시오.
    
    [User Profile]
    {profile_str}
    
    [Current System Context]
    {initial_context}
    """
    
    history = [] 

    while True:
        try:
            user_input = input("\n>> User: ").strip()
        except KeyboardInterrupt:
            return "EXIT"

        if not user_input: continue
        if user_input.lower() in ['q', 'exit', 'quit']: return "EXIT"
        
        # 3. 사용자 의도 파악 및 데이터 인출 (RAG & Tool Use)
        injected_context = ""

        # (A) 알림/감시 요청 감지 [신규 기능]
        alert_keywords = ["알림", "알려줘", "감시", "오르면", "내리면", "도달하면"]
        if any(k in user_input for k in alert_keywords):
            print(" [Mervis] 알림 설정 요청 분석 중...", end="")
            params = _extract_alert_params(user_input)
            
            if params:
                # 웹소켓 모듈에 감시 조건 등록
                ticker = params['ticker'].upper()
                price = params['price']
                cond = params['condition']
                
                # 실제 등록 함수 호출
                kis_websocket.add_watch_condition(ticker, price, cond)
                
                injected_context += f"\n[System Action] 사용자가 요청한 {ticker} ${price} ({cond}) 알림 설정을 완료했습니다. 사용자에게 설정됐다고 말해주십시오.\n"
                print(" 설정 완료.")
            else:
                print(" 실패 (조건 불명확).")

        # (B) 추천 요청 감지
        recommend_keywords = ["추천", "종목 좀", "살만한거", "뭐 살까", "유망", "급등"]
        is_recommendation = any(k in user_input for k in recommend_keywords)
        
        if is_recommendation:
            print(" [Mervis] DB 내 유망 종목 검색 중...", end="")
            rec_data = _get_recommendation_context(limit=3)
            injected_context += f"\n{rec_data}\n"
            print(" 완료.")

        # (C) 종목 분석 요청 감지
        # 1. 영어 티커 추출
        potential_tickers = re.findall(r'\b[A-Z]{2,5}\b', user_input.upper())
        # 2. (옵션) 한글 종목명 매핑 로직이 필요하다면 여기에 추가
        
        if potential_tickers:
            print(f" [Mervis] 데이터 분석: {potential_tickers}")
            for t in potential_tickers:
                res = mervis_brain.analyze_stock({'code': t, 'name': t, 'price': 0})
                if res:
                    injected_context += f"\n[Analysis Data for {t}]\n{res['report']}\n"
        
        # 4. 프롬프트 조립
        full_prompt = f"{system_instruction}\n"
        
        # 이전 대화 요약 (토큰 절약)
        for h in history[-4:]: 
            full_prompt += f"{h}\n"
            
        if injected_context:
            full_prompt += f"\n[Injecting Real-time Data & Actions]\n{injected_context}\n"
        
        full_prompt += f"User: {user_input}\nMervis:"
        
        try:
            # 5. Gemini 응답 생성
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            answer = response.text.strip()
            print(f"Mervis: {answer}")
            
            # 대화 기록 저장
            history.append(f"User: {user_input}")
            history.append(f"Mervis: {answer}")
            
            if len(user_input) > 10:
                mervis_profile.update_user_profile(user_input)
                
        except Exception as e:
            print(f"[System Error] 응답 생성 실패: {e}")