from google import genai
import secret
import mervis_profile 
import mervis_bigquery 
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
    analyzed_list = mervis_bigquery.get_analyzed_ticker_list() # 전체 조회
    analyzed_str = ", ".join(analyzed_list) if analyzed_list else "없음"

    print(f"[System] 사용자 프로필 로드 완료 (성향: {user_data.get('investment_style', 'Unknown')})")
    print(f"[System] 분석 기억 로드 완료 (총 {len(analyzed_list)}개 종목 보유)")

    initial_prompt = f"""
    당신은 사용자의 주식 비서 '머비스(Mervis)'입니다.
    이모티콘을 절대 사용하지 말고, 전문적이고 명확한 사무적인 말투로 대화하십시오.
    
    [System Memory - Index]
    당신은 현재 다음 {len(analyzed_list)}개 종목에 대한 분석 데이터를 DB에 보유하고 있습니다:
    [{analyzed_str}]
    
    * 사용자가 특정 종목에 대해 물어보면, 시스템이 해당 종목의 상세 리포트를 제공할 것입니다. 그 데이터를 바탕으로 답변하십시오.
    * 만약 사용자가 "보유한 종목 브리핑해줘"라고 하면, 위 리스트를 나열하고 어떤 종목의 상세 정보가 궁금한지 되물으십시오.
    
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
        
        # 3. [NEW] 문맥 감지 및 기억 인출 (Memory Injection)
        # 사용자가 입력한 문장에 '내가 아는 종목(analyzed_list)'이 포함되어 있는지 확인
        injected_memory = ""
        found_tickers = []
        
        if analyzed_list:
            upper_input = user_input.upper()
            for ticker in analyzed_list:
                # 사용자가 티커를 언급했는지 확인 (단어 단위 매칭 권장하지만 일단 단순 포함 여부 확인)
                if ticker in upper_input:
                    found_tickers.append(ticker)
            
            # 언급된 종목이 있다면, DB에서 상세 리포트를 가져와서 프롬프트에 주입
            if found_tickers:
                print(f" [System] '{', '.join(found_tickers)}' 상세 데이터 인출 중...", end="")
                for t in found_tickers:
                    mem = mervis_bigquery.get_recent_memory(t)
                    if mem:
                        injected_memory += f"\n[Detail Memory for {t} ({mem['date']})]\n{mem['report']}\n----------------\n"
                print(" 완료.")

        # 4. 실시간 프로필 학습
        if len(user_input) >= 4:
            try:
                update_result = mervis_profile.update_user_profile(user_input)
                if "successfully" in update_result:
                    print(" [System] User Profile Updated.")
            except: pass 

        # 프롬프트 구성 (인출된 기억이 있으면 포함)
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
            
            # 대화 기록 업데이트 (인젝션 된 내용은 히스토리에 너무 쌓이면 무거우므로 답변만 기록)
            history += f"\n사용자: {user_input}\n머비스: {answer}"
            
        except Exception as e:
            print(f"[오류] 답변 생성 실패: {e}")