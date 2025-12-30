from google import genai
import secret
import mervis_profile 
import mervis_bigquery 
import mervis_brain # [NEW] 대화 중 분석을 위해 두뇌 모듈 연결
import json

client = genai.Client(api_key=secret.GEMINI_API_KEY)

def start_consulting(report):
    print("\n" + "="*40)
    print("[머비스] 상담 모드 (종료: q, 재스캔: scan)")
    print("==================================================")
    
    # 1. 사용자 프로필 로드
    user_data = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_data, indent=2, ensure_ascii=False)
    
    # 2. BigQuery에서 '내가 아는(분석한) 종목 리스트' 전체 가져오기
    analyzed_list = mervis_bigquery.get_analyzed_ticker_list()
    analyzed_str = ", ".join(analyzed_list) if analyzed_list else "없음"

    print(f"[System] 사용자 프로필 로드 완료 (성향: {user_data.get('investment_style', 'Unknown')})")
    print(f"[System] 분석 기억 로드 완료 (총 {len(analyzed_list)}개 종목 보유)")

    initial_prompt = f"""
    당신은 사용자의 주식 비서 '머비스(Mervis)'입니다.
    이모티콘을 절대 사용하지 말고, 전문적이고 명확한 사무적인 말투로 대화하십시오.
    
    [System Memory - Index]
    당신은 현재 다음 종목들에 대한 분석 기록을 가지고 있습니다:
    [{analyzed_str}]
    
    * 사용자가 특정 종목을 언급하면 DB에서 불러온 [Detail Memory]를 참고하여 답변하십시오.
    * 만약 리스트에 없는 종목이라도, 사용자가 "분석해줘"라고 요청하면 시스템이 실시간으로 분석을 수행하고 정보를 제공할 것입니다. 잠시 기다리라고 안내하십시오.
    
    [User Profile]
    {profile_str}
    
    [Current Report Context]
    {report}
    """
    
    history = initial_prompt

    while True:
        try:
            user_input = input("\n>> 사용자: ").strip()
        except KeyboardInterrupt:
            return "EXIT"

        if not user_input: continue
        if user_input.lower() in ['q', 'exit', 'quit']: return "EXIT"
        if user_input.lower() == 'scan': return "SCAN"
        
        # 3. [NEW] 실시간 분석 트리거 & 기억 인출 로직
        injected_memory = ""
        found_tickers = []
        
        # 입력된 텍스트에서 대문자로 된 영단어(티커 후보) 추출을 시도하거나, 
        # 기존 analyzed_list와 매칭 + 혹은 새로운 티커라도 감지 시도
        # 여기서는 간단히 사용자 입력에서 티커를 추정합니다.
        
        # 3-1. 티커 감지 (기존 목록 + 입력된 단어 중 3~5글자 영어)
        words = user_input.upper().split()
        potential_tickers = [w for w in words if w.isalpha() and 2 <= len(w) <= 5]
        
        # 3-2. 분석 트리거 키워드 확인
        trigger_keywords = ["분석", "지금", "어때", "봐줘", "확인", "점검", "가격", "매수", "매도"]
        needs_analysis = any(k in user_input for k in trigger_keywords)

        for t in potential_tickers:
            # (A) 이미 아는 종목이거나, (B) 몰라도 분석을 요청한 경우
            if t in analyzed_list or (needs_analysis and t not in ["SCAN", "EXIT", "QUIT"]):
                found_tickers.append(t)

        if found_tickers:
            # 사용자가 '분석'을 원하면 즉시 두뇌 가동
            if needs_analysis:
                print(f" [System] 실시간 분석 요청 감지: {found_tickers}")
                for t in found_tickers:
                    print(f" [Mervis] '{t}' 최신 데이터 분석 중 (KIS API)...")
                    # mervis_brain 호출 (저장까지 자동으로 됨)
                    mervis_brain.analyze_stock({'code': t, 'name': t, 'price': 0})
                    # 분석 후 리스트 갱신 (새로운 종목일 수 있으므로)
                    if t not in analyzed_list: analyzed_list.append(t)
            
            # DB에서 (방금 업데이트된 것 포함) 최신 기억 인출
            print(f" [System] '{', '.join(found_tickers)}' 상세 데이터 인출 중...", end="")
            for t in found_tickers:
                mem = mervis_bigquery.get_recent_memory(t)
                if mem:
                    injected_memory += f"\n[Detail Memory for {t} ({mem['date']}) - Latest]\n{mem['report']}\n----------------\n"
            print(" 완료.")

        # 4. 실시간 프로필 학습
        if len(user_input) >= 4:
            try:
                update_result = mervis_profile.update_user_profile(user_input)
                if "successfully" in update_result:
                    print(" [System] User Profile Updated.")
            except: pass 

        # 프롬프트 구성
        if injected_memory:
            full_prompt = f"{history}\n[System Injection - Retrieved Memories]{injected_memory}\n사용자: {user_input}\n머비스:"
        else:
            full_prompt = f"{history}\n사용자: {user_input}\n머비스:"
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            answer = response.text.strip()
            print(f"머비스: {answer}")
            
            history += f"\n사용자: {user_input}\n머비스: {answer}"
            
        except Exception as e:
            print(f"[오류] 답변 생성 실패: {e}")