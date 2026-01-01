import requests
import json
import secret
import time
import os
import mervis_state

# 토큰 정보를 저장할 로컬 파일 경로
CACHE_FILE = "mervis_token_cache.json"

def load_cache():
    """파일에서 토큰 및 키 정보를 읽어옴"""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_cache(data):
    """토큰 및 키 정보를 파일에 저장함"""
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
    
    # 유효기간이 10분(600초) 이상 남았으면 재활용
    if saved_token and (expire_time - current_time > 600):
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
        print(f"[인증] {mode} 서버로부터 새로운 Access Token을 발급받습니다...")
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            new_token = data['access_token']
            
            # 유효기간 계산 (기본값 24시간)
            expires_in = int(data.get('expires_in', 86400))
            new_expire_time = current_time + expires_in
            
            # 캐시 업데이트 및 저장
            if mode not in cache: cache[mode] = {}
            cache[mode]["token"] = new_token
            cache[mode]["expire_time"] = new_expire_time
            
            save_cache(cache)
            
            print(f"[인증] 토큰 발급 완료. (만료: {expires_in}초 후)")
            return new_token
        else:
            print(f"[인증실패] {mode} 모드: {res.text}")
            return None
            
    except Exception as e:
        print(f"[인증오류] 통신 장애: {e}")
        return None

def get_websocket_key():
    mode = mervis_state.get_mode()
    
    # 1. 디스크 캐시 확인
    cache = load_cache()
    mode_cache = cache.get(mode, {})
    
    saved_ws_key = mode_cache.get("approval_key")
    ws_key_time = mode_cache.get("approval_key_time", 0)
    current_time = time.time()

    # 발급된 지 20시간(72000초) 이내라면 재사용
    if saved_ws_key and (current_time - ws_key_time < 72000):
        return saved_ws_key

    # 2. 신규 키 발급 요청
    if mode == "REAL":
        base_url = secret.URL_REAL
        app_key = secret.APP_KEY_REAL
        app_secret = secret.APP_SECRET_REAL
    else:
        base_url = secret.URL_MOCK
        app_key = secret.APP_KEY_MOCK
        app_secret = secret.APP_SECRET_MOCK

    path = "oauth2/Approval"
    url = f"{base_url}/{path}"
    
    headers = {"content-type": "application/json; utf-8"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret # 웹소켓 키 발급 시에는 파라미터명이 secretkey임
    }
    
    try:
        print(f"[인증] {mode} 서버로부터 새로운 WebSocket Key를 발급받습니다...")
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            new_key = data['approval_key']
            
            # 캐시 업데이트 및 저장
            if mode not in cache: cache[mode] = {}
            cache[mode]["approval_key"] = new_key
            cache[mode]["approval_key_time"] = current_time
            
            save_cache(cache)
            
            print(f"[인증] 웹소켓 키 발급 완료.")
            return new_key
        else:
            print(f"[인증실패] WS Key 발급 실패: {res.text}")
            return None
    except Exception as e:
        print(f"[인증오류] 통신 장애: {e}")
        return None