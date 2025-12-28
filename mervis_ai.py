from google import genai
import secret

client = genai.Client(api_key=secret.GEMINI_API_KEY)

def start_consulting(report):
    print("\n" + "="*40)
    print("[머비스] 상담 모드 (종료: q, 재스캔: scan)")
    print("="*40)
    
    # [수정] 변수 초기화 명시
    history = ""
    initial_prompt = f"""
    당신은 민동일 님의 주식 비서 '머비스'입니다.
    이모티콘을 쓰지 말고 전문적인 어조로 대화하십시오.
    
    [최신 분석 리포트 요약]
    {report}
    """
    
    # 대화 문맥에 리포트 주입
    history = initial_prompt

    while True:
        try:
            user_input = input("\n민동일: ")
        except KeyboardInterrupt:
            return "EXIT"

        if user_input.lower() == 'q': return "EXIT"
        if user_input.lower() == 'scan': return "SCAN"
        
        # 프롬프트 구성
        full_prompt = f"{history}\n사용자: {user_input}\n머비스:"
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            
            answer = response.text.strip()
            print(f"머비스: {answer}")
            
            # 대화 기록 업데이트 (너무 길어지면 앞부분 자르는 로직 추가 가능)
            history += f"\n사용자: {user_input}\n머비스: {answer}"
            
        except Exception as e:
            print(f"[오류] 답변 생성 실패: {e}")
            # 오류가 나도 루프가 안 깨지도록 유지