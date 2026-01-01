from google import genai
import secret
import json
import os
from datetime import datetime
import mervis_bigquery 

client = genai.Client(api_key=secret.GEMINI_API_KEY)
USER_DATA_FILE = "mervis_user_data.json"

# [V13.0] 로컬 파일 초기화 (공통 함수)
def _reset_local_file():
    default_data = {
        "investment_style": "Unidentified", 
        "goals": [], 
        "portfolio": {}, 
        "history_summary": [], 
        "risk_tolerance": "Medium", 
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(default_data, f, indent=4, ensure_ascii=False)
    return default_data

# [기존] 로컬 데이터 없으면 생성
def init_user_data():
    if not os.path.exists(USER_DATA_FILE):
        _reset_local_file()

# [V13.0 NEW] 프로필 강제 초기화 함수
def reset_profile():
    # 1. 로컬 파일 초기화
    new_data = _reset_local_file()
    
    # 2. BigQuery 초기화 (덮어쓰기)
    mervis_bigquery.save_profile(new_data)
    
    print("[System] User Profile has been completely RESET.")
    return "사용자 프로필이 초기화되었습니다. 새로운 투자 성향을 말씀해 주세요."

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

# [V12.5 유지] 유저 성향에서 '스캔용 키워드' 추출
def get_preference_tags():
    """
    유저 프로필을 분석하여 kis_scan에서 사용할 섹터/테마 태그를 반환
    """
    profile = get_user_profile()
    tags = set()
    
    # 1. 투자 스타일 및 위험 감수도 분석
    style = str(profile.get("investment_style", "")).lower()
    risk = str(profile.get("risk_tolerance", "")).lower()
    
    # 공격적/고위험 -> 레버리지, 기술주, 코인
    if any(x in style for x in ["aggressive", "공격", "active"]) or \
       any(x in risk for x in ["high", "높음"]):
        tags.update(["LEV", "TECH", "COIN", "SEMI"])
        
    # 안정적/보수적 -> 배당, 소비재, 방산
    if any(x in style for x in ["stable", "안정", "passive", "long"]) or \
       any(x in risk for x in ["low", "낮음"]):
        tags.update(["DIV", "CONS", "DEF", "MACRO"])

    # 2. 목표 및 대화 내역에서 구체적 키워드 매칭
    goals = str(profile.get("goals", [])).lower()
    history = str(profile.get("history_summary", "")).lower()
    combined_text = goals + " " + history

    # 키워드 매핑 테이블
    keyword_map = {
        "ai": ["SEMI", "TECH"],
        "bio": ["BIO"],
        "car": ["EV", "TECH"],
        "div": ["DIV"],
        "gold": ["MACRO"],
        "war": ["DEF"],
        "coin": ["COIN"],
        "crypto": ["COIN"]
    }

    for key, mapped_tags in keyword_map.items():
        if key in combined_text:
            tags.update(mapped_tags)

    # 기본값이 없으면 우량주(TECH)와 시장지수(MACRO) 추가
    if not tags:
        tags.update(["TECH", "MACRO"])
        
    return list(tags)

# [V13.0 수정] 스마트 프로필 업데이트 (초기화 트리거 추가)
def update_user_profile(interaction_text, action_type="conversation"):
    # [V13.0] 초기화 명령어 감지
    if "초기화" in interaction_text and "프로필" in interaction_text:
        return reset_profile()

    if len(interaction_text) < 4 or interaction_text in ["아니", "응", "그래", "삭제", "scan"]:
        return "Skipped (Too short)"

    current_profile = get_user_profile()
    
    prompt = f"""
    Role: User Analyst.
    Task: Update User Profile based on new interaction.
    
    [Current Profile]
    {json.dumps(current_profile, indent=2, ensure_ascii=False)}
    
    [New Interaction]
    "{interaction_text}"
    
    [Rules]
    1. Ignore complaints or simple commands.
    2. Extract explicit preferences (e.g., "I like AI stocks", "Stop trading volatile stocks").
    3. Return "SKIP" if no meaningful info.
    4. Otherwise, return ONLY the updated JSON.
    """
    
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        response_text = res.text.strip()
        
        if "SKIP" in response_text:
            return "Skipped (No meaningful info)"
            
        cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
        updated_data = json.loads(cleaned_text)
        updated_data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        mervis_bigquery.save_profile(updated_data)
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
            
        return "User profile updated successfully."
    except Exception as e:
        return f"Failed to update profile: {e}"

# [기존] 일관성 체크
def check_consistency(strategy_report):
    profile = get_user_profile()
    prompt = f"""
    Role: Risk Manager.
    Profile: {profile.get('investment_style')}, {profile.get('risk_tolerance')}
    Strategy: {strategy_report}
    Output: Warning in Korean if risky, else "PASS".
    """
    try:
        res = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return res.text.strip()
    except:
        return "PASS"