print("--- Mervis Loading... ---")
import kis_scan
import mervis_brain
import mervis_ai
import mervis_state
import time
import sys
import mervis_profile

def run_system():
    # [수정 1] 배너 간소화
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
        
        menu = input(">> 입력: ")
        
        results = []
        
        if menu == '1':
            try:
                targets = kis_scan.get_dynamic_targets()
                
                if not targets:
                    print("[대기] 분석 대상 없음. 5초 후 재시도.")
                    time.sleep(5)
                    continue
                    
                print(f"\n[머비스] 총 {len(targets)}개 종목 분석 시작. (중단: Ctrl+C)")
                
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
                print(" -> [실패] 티커를 확인하거나 데이터를 가져올 수 없습니다.")

        # [수정 2] 대화 모드 (데이터 분석 없이 바로 상담 진입)
        elif menu == '3':
            print("[머비스] 대화 모드로 진입합니다. (종료: 'exit')")
            # 분석 리포트 대신 대화 모드임을 알리는 컨텍스트 전달
            context = "[System Info] User entered 'Free Talk' mode without new market data scan. Focus on consulting, profile review, or general investment philosophy."
            act = mervis_ai.start_consulting(context)
            if act == "EXIT":
                print("[시스템] 프로그램을 종료합니다.")
                sys.exit(0)
            continue # 대화 끝나면 다시 메뉴로

        elif menu == '4':
            print("[시스템] 프로그램을 종료합니다.")
            sys.exit(0)
            
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