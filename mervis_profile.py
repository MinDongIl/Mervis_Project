from google import genai
import secret
import json
import os
from datetime import datetime
import mervis_bigquery 

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_DATA_FILE = "mervis_user_data.json"

# [기존] 로컬 초기화
def init_user_data():
    if not os.path.exists(USER_DATA_FILE):
        default_data = {
            "investment_style": "Unidentified", 
            "goals": [], 
            "portfolio": {}, 
            "history_summary": [], 
            "risk_tolerance": "Medium", 
            "last_updated": ""
        }
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)

# [기존] 프로필 로드
def get_user_profile():
    bq_profile = mervis_bigquery.get_profile()
    if bq_profile:
        return bq_profile

    init_user_data()
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

# [수정] 스마트 프로필 업데이트 (필터링 추가)
def update_user_profile(interaction_text, action_type="conversation"):
    # 1. 너무 짧거나 의미 없는 말은 API 호출 없이 즉시 무시
    if len(interaction_text) < 4 or interaction_text in ["아니", "응", "그래", "삭제", "scan"]:
        return "Skipped (Too short)"

    current_profile = get_user_profile()
    
    # 2. AI에게 '판단'을 시킴: 이것이 프로필에 저장할 가치가 있는 정보인가?
    # 불만(Complaints), 단순 질문(Questions)은 저장하지 말라고 명시
    prompt = f"""
    Role: User Analyst.
    Task: Determine if the 'New Interaction' contains MEANINGFUL information about the user's investment style, goals, or constraints.
    
    [Current Profile]
    {json.dumps(current_profile, indent=2, ensure_ascii=False)}
    
    [New Interaction]
    "{interaction_text}"
    
    [Rules for Update]
    1. IGNORE simple questions (e.g., "Why?", "What is PLTR?").
    2. IGNORE complaints or commands (e.g., "Don't be stupid", "Shut up").
    3. ONLY extract explicit preferences or facts (e.g., "I hate volatility", "I own TSLA").
    4. If NO new info is found, return exactly: "SKIP"
    5. If new info exists, return ONLY the updated JSON.
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        response_text = res.text.strip()
        
        # AI가 SKIP이라고 판단하면 저장 로직을 태우지 않음
        if "SKIP" in response_text:
            return "Skipped (No meaningful info)"
            
        # JSON 파싱
        cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
        updated_data = json.loads(cleaned_text)
        
        updated_data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # BigQuery 및 로컬 저장
        mervis_bigquery.save_profile(updated_data)
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
            
        return "User profile updated successfully."
        
    except Exception as e:
        return f"Failed to update profile: {e}"

# [기존 유지] 일관성 체크
def check_consistency(strategy_report):
    profile = get_user_profile()
    prompt = f"""
    Role: Risk Manager.
    Task: Check strategy against user profile.
    Profile: {profile.get('investment_style')}, {profile.get('risk_tolerance')}
    Strategy: {strategy_report}
    Output: Warning in Korean if risky, else "PASS".
    """
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except:
        return "PASS"