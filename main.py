import kis_scan
import mervis_brain
import mervis_ai
import mervis_state
import time
import sys  # [추가] 강제 종료를 위해 필요

def run_system():
    print("==================================================")
    print(" [MERVIS] Intelligent Investment System V8.2")
    print("==================================================")
    print(" [1] 실전 모드 (Real)")
    print(" [2] 모의 모드 (Mock)")
    
    c = input(">> 선택 (1/2): ")
    mervis_state.set_mode(c)
    
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    print(f"\n[시스템] '{mode_name}' 모드로 시작합니다.")
    
    while True:
        results = [] # 변수 선언 위치 수정 (오류 방지)
        
        try:
            targets = kis_scan.get_dynamic_targets()
            
            if not targets:
                print("[대기] 분석 대상 없음. 5초 후 재시도.")
                time.sleep(5)
                continue
                
            print(f"\n[머비스] 총 {len(targets)}개 종목 분석 시작. (중단: Ctrl+C)")
            
            for i, item in enumerate(targets):
                print(f"[{i+1}/{len(targets)}] {item['code']} 분석 중...", end="")
                
                res = mervis_brain.analyze_stock(item)
                
                if res:
                    results.append(res)
                    print(" -> [완료]")
                else:
                    print(" -> [실패]")
                
        except KeyboardInterrupt:
            # [수정된 부분] 여기서 종료 여부를 확실히 묻습니다.
            print("\n\n[일시정지] 사용자 중단 명령이 감지되었습니다.")
            choice = input(">> 프로그램을 완전히 종료하시겠습니까? (y=종료 / n=상담이동): ")
            
            if choice.lower() == 'y':
                print("[시스템] 프로그램을 안전하게 종료합니다.")
                sys.exit(0) # 강제 종료
            else:
                print("[시스템] 현재까지 분석된 데이터로 상담을 시작합니다.")
        
        # 분석 결과가 하나도 없으면 다시 스캔
        if not results:
            continue
        
        full_report = f"[{mode_name} 리포트]\n"
        for r in results:
            full_report += f"[{r['code']}]: {r['report']}\n---\n"
            
        # 상담 모드 실행
        act = mervis_ai.start_consulting(full_report)
        
        if act == "EXIT":
            print("[시스템] 프로그램을 종료합니다.")
            sys.exit(0) # 강제 종료
        elif act == "SCAN":
            print("[시스템] 다시 시장을 스캔합니다.")
            continue

if __name__ == "__main__":
    run_system()