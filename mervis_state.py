# [머비스 상태 관리자]
# 현재 시스템이 '실전 모드'인지 '모의 모드'인지 전역 관리

# 기본값 (실행 시 변경됨)
CURRENT_MODE = "REAL" 

def set_mode(mode_input):
    global CURRENT_MODE
    if mode_input in ["1", "real", "REAL"]:
        CURRENT_MODE = "REAL"
    else:
        CURRENT_MODE = "MOCK"

def get_mode():
    return CURRENT_MODE

def is_real():
    return CURRENT_MODE == "REAL"