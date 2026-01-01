print("--- Mervis Loading... ---")
import kis_scan
import mervis_brain
import mervis_ai
import mervis_state
import time
import sys
import mervis_profile
import mervis_bigquery
import update_volume_tier
import kis_websocket # [NEW] 웹소켓 모듈 추가

def system_init():
    print("==================================================")
    print(" [MERVIS] System Initialization Check")
    print("==================================================")
    
    # DB 최신화 상태 점검 (Smart Auto-Run)
    print(" [Check] Checking DB Freshness...", end=" ")
    is_fresh = mervis_bigquery.check_db_freshness()
    
    if is_fresh:
        print("[PASS] DB is up-to-date.")
    else:
        print("[UPDATE REQUIRED]")
        print("\n [Notice] DB outdated. Running Daily Volume Analysis...")
        print("          (This may take 1-2 minutes. Please wait...)\n")
        
        try:
            update_volume_tier.update_volume_data()
            print("\n [System] DB Update Complete. Starting Main System.")
        except Exception as e:
            print(f"\n [Warning] Update failed ({e}). Proceeding with existing data.")
            
    print("==================================================\n")

def run_system():
    # 1. 시스템 초기화
    system_init()

    # 2. 메인 화면 출력
    print("==================================================")
    print(" [MERVIS] System Online")
    print("==================================================")
    
    try:
        profile = mervis_profile.get_user_profile()
        style = profile.get('investment_style', 'Unknown')
        updated = profile.get('last_updated', 'N/A')
        print(f" [User Profile] Style: '{style}' | Updated: {updated}")
    except Exception as e:
        print(f" [Warning] Profile load failed: {e}")

    print("==================================================")
    print(" [1] 실전 모드 (Real)")
    print(" [2] 모의 모드 (Mock)")
    
    c = input(">> 선택 (1/2): ")
    mervis_state.set_mode(c)
    
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    print(f"\n[시스템] '{mode_name}' 모드로 시작합니다.")
    
    while True:
        print(f"\n[{mode_name} 메인 메뉴]")
        print(" 1. 전체 시장 자동 스캔 (Auto Scan)")
        print(" 2. 특정 종목 검색 (Sniper Search)")
        print(" 3. 대화 모드 (Free Talk)")
        print(" 4. 종료 (Exit)")
        print(" 5. 실시간 감시 모드 (Real-time Watch) [NEW]") # [NEW]
        
        menu = input(">> 입력: ")
        
        results = []
        
        if menu == '1':
            try:
                targets = kis_scan.get_dynamic_targets()
                
                if not targets:
                    print("[대기] 분석 대상 없음. 5초 후 재시도.")
                    time.sleep(5)
                    continue
                    
                print(f"\n[머비스] 총 {len(targets)}개 핵심 종목 분석 시작. (중단: Ctrl+C)")
                
                for i, item in enumerate(targets):
                    print(f"[{i+1}/{len(targets)}] {item['code']} 분석 중...", end="")
                    sys.stdout.flush()
                    res = mervis_brain.analyze_stock(item)
                    if res:
                        results.append(res)
                        print(" -> [완료]")
                    else:
                        print(" -> [실패]")
            except KeyboardInterrupt:
                print("\n[중단] 스캔을 멈춥니다.")
        
        elif menu == '2':
            code = input(">> 분석할 종목 티커 입력 : ").upper().strip()
            if not code: continue
            print(f"[머비스] '{code}' 정밀 분석 시작...", end="")
            sys.stdout.flush()
            target_item = {"code": code, "name": "Manual Search", "price": 0}
            res = mervis_brain.analyze_stock(target_item)
            if res:
                results.append(res)
                print(" -> [완료]")
            else:
                print(" -> [실패]")

        elif menu == '3':
            print("[머비스] 대화 모드로 진입합니다. (종료: 'exit')")
            context = "[System Info] User entered 'Free Talk' mode."
            act = mervis_ai.start_consulting(context)
            if act == "EXIT":
                print("[시스템] 프로그램을 종료합니다.")
                sys.exit(0)
            continue 

        elif menu == '4':
            print("[시스템] 프로그램을 종료합니다.")
            sys.exit(0)

        # [NEW] 실시간 감시 모드
        elif menu == '5':
            print("\n[머비스] 실시간 감시 모드를 준비합니다...")
            
            # 1. 감시 대상 로딩 (Scan 모듈 활용)
            targets = kis_scan.get_dynamic_targets()
            if not targets:
                print("[오류] 감시할 대상이 없습니다. DB 상태를 확인하세요.")
                continue
                
            print(f"[시스템] 감시 대상: {len(targets)}개 종목")
            print("[시스템] 웹소켓 연결 시도 중... (중단: Ctrl+C)")
            
            # 2. 웹소켓 실행 (Blocking)
            kis_websocket.run_monitoring(targets)
            continue # 감시 끝나면 메뉴로 복귀
            
        else:
            print("[알림] 올바른 메뉴를 선택해주세요.")
            continue
        
        # 1, 2번 메뉴 실행 결과가 있을 때만 상담 진행
        if not results:
            continue
        
        full_report = f"[{mode_name} 리포트]\n"
        for r in results:
            full_report += f"[{r['code']}]: {r['report']}\n---\n"
            
        act = mervis_ai.start_consulting(full_report)
        
        if act == "EXIT":
            print("[시스템] 프로그램을 종료합니다.")
            sys.exit(0)

if __name__ == "__main__":
    run_system()