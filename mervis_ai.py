from google import genai
import secret
import mervis_profile  # [NEW] 사용자 프로필 연동
import json

client = genai.Client(api_key=secret.GEMINI_API_KEY)

def start_consulting(report):
    print("\n" + "="*40)
    print("[머비스] 상담 모드 (종료: q, 재스캔: scan)")
    print("==================================================")
    
    # 1. [NEW] 사용자 프로필 로드
    user_data = mervis_profile.get_user_profile()
    # JSON 형태의 문자열로 변환하여 프롬프트에 주입
    profile_str = json.dumps(user_data, indent=2, ensure_ascii=False)
    
    print(f"[System] 사용자 프로필 로드 완료 (성향: {user_data.get('investment_style', 'Unknown')})")

    history = ""
    initial_prompt = f"""
    당신은 민동일 님의 주식 비서 '머비스'입니다.
    이모티콘을 절대 사용하지 말고, 전문적이고 간결한 비서의 말투로 대화하십시오.
    
    [사용자 프로필 (User Persona)]
    이 정보를 바탕으로 사용자에게 맞춤형 조언을 제공하십시오.
    {profile_str}
    
    [최신 분석 리포트 요약]
    {report}
    """
    
    # 대화 문맥 초기화
    history = initial_prompt

    while True:
        try:
            user_input = input("\n민동일: ").strip()
        except KeyboardInterrupt:
            return "EXIT"

        if not user_input: continue
        if user_input.lower() in ['q', 'exit', 'quit']: return "EXIT"
        if user_input.lower() == 'scan': return "SCAN"
        
        # 2. [NEW] 실시간 학습 (사용자 발언 분석 및 프로필 업데이트)
        # 너무 짧은 단답형(네, 아니오 등)은 제외하고 학습하여 효율성 확보
        if len(user_input) >= 4:
            # 사용자가 인지하지 못하게 백그라운드에서 조용히 수행
            try:
                mervis_profile.update_user_profile(user_input)
            except Exception:
                pass # 학습 오류가 대화를 방해하지 않도록 무시

        # 프롬프트 구성
        full_prompt = f"{history}\n사용자: {user_input}\n머비스:"
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            answer = response.text.strip()
            print(f"머비스: {answer}")
            
            # 대화 기록 업데이트
            # (Context Window 관리를 위해 너무 옛날 대화는 잘라내는 로직을 추후 추가 가능)
            history += f"\n사용자: {user_input}\n머비스: {answer}"
            
        except Exception as e:
            print(f"[오류] 답변 생성 실패: {e}")