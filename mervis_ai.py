from google import genai
import secret
import mervis_profile 
import mervis_bigquery # [NEW] 기억 연동
import json

client = genai.Client(api_key=secret.GEMINI_API_KEY)

def start_consulting(report):
    print("\n" + "="*40)
    print("[머비스] 상담 모드 (종료: q, 재스캔: scan)")
    print("==================================================")
    
    # 1. 사용자 프로필 로드
    user_data = mervis_profile.get_user_profile()
    profile_str = json.dumps(user_data, indent=2, ensure_ascii=False)
    
    # 2. [NEW] BigQuery에서 '내가 아는(분석한) 종목 리스트' 가져오기
    # 최근 7일간 분석한 종목 리스트를 가져와서 프롬프트에 넣어줌
    analyzed_list = mervis_bigquery.get_analyzed_ticker_list(days=7)
    analyzed_str = ", ".join(analyzed_list) if analyzed_list else "없음"

    print(f"[System] 사용자 프로필 로드 완료 (성향: {user_data.get('investment_style', 'Unknown')})")
    print(f"[System] 분석 기억 로드 완료 ({len(analyzed_list)}개 종목)")

    # [수정] 이름 하드코딩 제거 및 기억 정보 주입
    initial_prompt = f"""
    당신은 사용자의 주식 비서 '머비스(Mervis)'입니다.
    이모티콘을 절대 사용하지 말고, 전문적이고 명확한 사무적인 말투로 대화하십시오.
    
    [System Memory - Analyzed Stocks]
    현재 당신의 데이터베이스(BigQuery)에는 다음 종목들에 대한 최신 분석 데이터가 저장되어 있습니다:
    [{analyzed_str}]
    * 사용자가 "분석한 거 다 말해봐"라고 하면 위 리스트를 참고하여 대답하십시오.
    * 위 리스트에 없는 종목을 분석했다고 거짓말하지 마십시오.
    
    [User Profile (User Persona)]
    {profile_str}
    
    [Current Report Summary]
    {report}
    """
    
    history = initial_prompt

    while True:
        try:
            # [수정] 하드코딩된 이름 제거 -> 일반적인 표기로 변경
            user_input = input("\n>> 사용자: ").strip()
        except KeyboardInterrupt:
            return "EXIT"

        if not user_input: continue
        if user_input.lower() in ['q', 'exit', 'quit']: return "EXIT"
        if user_input.lower() == 'scan': return "SCAN"
        
        # 3. [NEW] 실시간 학습 (필터링 적용됨)
        # 이제 의미 있는 정보일 때만 로그가 출력됩니다.
        if len(user_input) >= 4:
            try:
                update_result = mervis_profile.update_user_profile(user_input)
                # 업데이트 성공 시에만 짧게 로그 출력
                if "successfully" in update_result:
                    print(" [System] User Profile Updated.")
            except Exception:
                pass 

        # 프롬프트 구성
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