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
import kis_websocket
import kis_account

def system_init():
    print("==================================================")
    print(" [MERVIS] System Initialization Check")
    print("==================================================")
    
    # DB 최신화 상태 점검
    print(" [Check] Checking DB Freshness...", end=" ")
    is_fresh = mervis_bigquery.check_db_freshness()
    
    if is_fresh:
        print("[PASS] DB is up-to-date.")
    else:
        print("[UPDATE REQUIRED]")
        print("\n [Notice] DB outdated. Running Daily Volume Analysis...")
        try:
            update_volume_tier.update_volume_data()
            print("\n [System] DB Update Complete. Starting Main System.")
        except Exception as e:
            print(f"\n [Warning] Update failed ({e}). Proceeding...")
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
        print(f" [User Profile] Style: '{style}'")
    except: pass

    print("==================================================")
    print(" [1] 실전 모드 (Real)")
    print(" [2] 모의 모드 (Mock)")
    
    c = input(">> 선택 (1/2): ")
    mervis_state.set_mode(c)
    
    mode_name = "실전(REAL)" if mervis_state.is_real() else "모의(MOCK)"
    print(f"\n[시스템] '{mode_name}' 모드로 시작합니다.")

    # 자산 현황 체크 및 DB 저장
    print(f"\n[System] '{mode_name}' 자산 현황 동기화 중...")
    try:
        my_asset = kis_account.get_my_total_assets()
        if my_asset:
            print(f" -> 총 자산: ${my_asset['total']} | 수익률: {my_asset['pnl']}%")
            
            mervis_bigquery.save_daily_balance(
                total_asset=my_asset['total'],
                cash=my_asset['cash'],
                stock_val=my_asset['stock'],
                pnl_daily=my_asset['pnl']
            )
        else:
            print(" -> [Warning] 자산 조회 실패 (API 응답 없음)")
    except Exception as e:
        print(f" -> [Error] 자산 동기화 중 오류: {e}")
    
    while True:
        # 감시 상태 표시
        monitor_status = "ON" if kis_websocket.is_active() else "OFF"

        print(f"\n[{mode_name} 메인 메뉴] | 감시 상태: {monitor_status}")
        print(" 1. 전체 시장 자동 스캔 (Auto Scan)")
        print(" 2. 특정 종목 검색 (Sniper Search)")
        print(" 3. 대화 모드 (Free Talk)")
        print(" 4. 종료 (Exit)")
        
        # 감시 상태에 따라 메뉴 텍스트 변경
        if kis_websocket.is_active():
            print(" 5. 실시간 감시 중단 (Stop Monitoring)")
        else:
            print(" 5. 실시간 감시 시작 (Start Monitoring)")
        
        menu = input(">> 입력: ")
        results = []
        
        if menu == '1':
            try:
                # DB 읽기 전용 호출 (키워드 자동 번역 적용)
                targets = mervis_bigquery.get_tickers_from_db(limit=40, tags=[]) 
                
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
            target_item = {"code": code, "name": "Manual Search", "price": 0}
            res = mervis_brain.analyze_stock(target_item)
            if res:
                results.append(res)
                print(" -> [완료]")
            else:
                print(" -> [실패]")

        elif menu == '3':
            print("[머비스] 대화 모드로 진입합니다. (종료: 'exit')")
            print(" * 백그라운드 감시 로그가 계속 출력될 수 있습니다.")
            context = f"[System] User in Free Talk. Monitor: {monitor_status}"
            act = mervis_ai.start_consulting(context)
            if act == "EXIT":
                print("[시스템] 프로그램을 종료합니다.")
                sys.exit(0)
            continue 

        elif menu == '4':
            kis_websocket.stop_monitoring()
            print("[시스템] 프로그램을 종료합니다.")
            sys.exit(0)

        elif menu == '5':
            if kis_websocket.is_active():
                kis_websocket.stop_monitoring()
            else:
                # DB에서 타겟 가져와서 시작
                targets = mervis_bigquery.get_tickers_from_db(limit=40)
                if targets:
                    kis_websocket.start_background_monitoring(targets)
                else:
                    print("[오류] 감시할 대상이 없습니다. 1번 스캔을 먼저 하세요.")
            continue
            
        else:
            print("[알림] 올바른 메뉴를 선택해주세요.")
            continue
        
        if results:
            full_report = f"[{mode_name} 리포트]\n"
            for r in results:
                full_report += f"[{r['code']}]: {r['report']}\n---\n"
            
            mervis_ai.start_consulting(full_report)

if __name__ == "__main__":
    run_system()