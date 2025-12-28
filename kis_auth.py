import requests
import json
import secret
import time
import os
import mervis_state

# [머비스 인증 시스템 V2.0 - 디스크 캐싱 적용]
# 토큰을 파일로 저장하여 프로그램 재시작 시에도 재활용

CACHE_FILE = "mervis_token_cache.json"

def load_cache():
    """파일에서 토큰 정보를 읽어옴"""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_cache(data):
    """토큰 정보를 파일에 저장함"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[시스템] 토큰 파일 저장 실패: {e}")

def get_access_token():
    mode = mervis_state.get_mode()
    
    # 1. 디스크 캐시 확인
    cache = load_cache()
    mode_cache = cache.get(mode, {})
    
    saved_token = mode_cache.get("token")
    expire_time = mode_cache.get("expire_time", 0)
    current_time = time.time()
    
    # 유효기간이 10분 이상 남았으면 재활용 (여유 있게 설정)
    if saved_token and (expire_time - current_time > 600):
        # 디버깅용: 저장된 토큰 사용 시엔 조용히 리턴 (로그 생략 가능)
        # print(f"[인증] 저장된 {mode} 토큰을 재사용합니다.") 
        return saved_token

    # 2. 토큰 만료 또는 없음 -> 신규 발급 요청
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    path = "oauth2/tokenP"
    url = f"{base_url}/{path}"
    
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    
    try:
        print(f"[인증] {mode} 서버로부터 새로운 토큰을 발급받습니다...")
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            new_token = data['access_token']
            
            # 유효기간 계산 (보통 expires_in은 초 단위, 기본값 86400초=24시간 가정)
            # 안전하게 API가 주는 만료시간보다 조금 짧게 잡음
            expires_in = int(data.get('expires_in', 86400))
            new_expire_time = current_time + expires_in
            
            # 파일에 저장
            cache[mode] = {
                "token": new_token,
                "expire_time": new_expire_time
            }
            save_cache(cache)
            
            print(f"[인증] 토큰 발급 완료. (만료: {expires_in}초 후)")
            return new_token
        else:
            print(f"[인증실패] {mode} 모드: {res.text}")
            return None
            
    except Exception as e:
        print(f"[인증오류] 통신 장애: {e}")
        return None