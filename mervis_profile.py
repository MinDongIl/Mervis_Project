from google import genai
import secret
import json
import os
from datetime import datetime
import mervis_bigquery # [NEW] BigQuery 모듈 연결

# 사용자 프로필 관리 모듈

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_DATA_FILE = "mervis_user_data.json"

# [초기화] 사용자 데이터 파일이 없으면 생성 (로컬 백업용)
def init_user_data():
    if not os.path.exists(USER_DATA_FILE):
        default_data = {
            "investment_style": "Unidentified", # 공격형/안정형 등
            "goals": [], # 목표 수익률, 목표 금액 등
            "portfolio": {}, # 보유 종목 및 비중
            "history_summary": [], # 과거 주요 행동 요약
            "risk_tolerance": "Medium", # 감내 가능 리스크
            "last_updated": ""
        }
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)

# [수정] 사용자 프로필 불러오기 (BigQuery 우선)
def get_user_profile():
    # 1. BigQuery에서 최신 프로필 조회 시도
    bq_profile = mervis_bigquery.get_profile()
    if bq_profile:
        return bq_profile

    # 2. BigQuery에 없으면 로컬 파일에서 로드 (백업/초기)
    init_user_data()
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

# [수정] 대화 내용이나 행동을 분석해 프로필 갱신 (BigQuery 저장 추가)
def update_user_profile(interaction_text, action_type="conversation"):
    current_profile = get_user_profile()
    
    prompt = f"""
    Role: User Analyst for AI Investment System.
    Task: Analyze the user's latest interaction and update their investment profile.
    
    [Current Profile]
    {json.dumps(current_profile, indent=2, ensure_ascii=False)}
    
    [New Interaction ({action_type})]
    "{interaction_text}"
    
    [Instruction]
    1. Update 'investment_style' if new evidence suggests a change (e.g., Aggressive, Conservative).
    2. Extract any specific 'goals' mentioned (e.g., "Earn 10M won").
    3. Update 'portfolio' or 'risk_tolerance' if mentioned.
    4. Add a brief one-line summary to 'history_summary' if it's a significant event (e.g., "Bought TSLA despite warning").
    5. Return ONLY the updated JSON.
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        
        # JSON 부분만 파싱
        response_text = res.text.replace("```json", "").replace("```", "").strip()
        updated_data = json.loads(response_text)
        
        updated_data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # [NEW] 1. BigQuery에 영구 저장
        mervis_bigquery.save_profile(updated_data)
        
        # [NEW] 2. 로컬 파일에도 백업 (오프라인/디버깅용)
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
            
        return "User profile updated successfully (Saved to BigQuery & Local)."
        
    except Exception as e:
        return f"Failed to update profile: {e}"

# [기존 유지] 전략이 사용자 성향과 맞는지 체크
def check_consistency(strategy_report):
    profile = get_user_profile()
    
    prompt = f"""
    Role: Risk Manager.
    Task: Check if the proposed strategy aligns with the user's profile.
    
    [User Profile]
    Style: {profile.get('investment_style')}
    Risk Tolerance: {profile.get('risk_tolerance')}
    History: {profile.get('history_summary')[-3:]}
    
    [Proposed Strategy]
    {strategy_report}
    
    [Output Requirement]
    If the strategy is too risky for this user or contradicts their goals, provide a short warning message in Korean.
    If it's okay, return "PASS".
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except:
        return "PASS"