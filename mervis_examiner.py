import mervis_bigquery
import kis_chart
import datetime
import mervis_state

def run_examination():
    """
    [채점관 실행 V2]
    BUY/SELL 적중률뿐만 아니라 HOLD(관망)의 기회비용/방어율까지 검증
    """
    print("\n" + "="*60)
    print(" [Examiner] 자기 복기 시스템 (전수 채점 가동)")
    print("="*60)
    
    # 데이터 정합성을 위해 실전 모드 강제
    mervis_state.set_mode("REAL")
    
    pending_list = mervis_bigquery.get_pending_trades()
    
    if not pending_list:
        print(" [Examiner] 채점할 대기 목록이 없습니다.")
        return

    print(f" [Examiner] 총 {len(pending_list)}건의 검증 대기 항목이 있습니다.")
    
    count_win = 0
    count_lose = 0
    count_pending = 0
    today = datetime.datetime.now().date()

    for item in pending_list:
        ticker = item['ticker']
        action = item['action']
        entry_price = item['entry_price']
        target = item['target']
        cut = item['cut']
        entry_date = item['date'] 
        
        # 차트 조회용 날짜 문자열
        start_date_str = entry_date.strftime("%Y%m%d")
        
        # 해당 종목 일봉 차트 조회
        daily_chart = kis_chart.get_daily_chart(ticker)
        if not daily_chart:
            print(f" -> [Skip] {ticker}: 차트 데이터 조회 실패")
            continue
            
        # 예측 시점 이후의 캔들만 필터링 & 정렬
        future_candles = []
        for candle in daily_chart:
            if candle['xymd'] >= start_date_str:
                future_candles.append(candle)
        future_candles.sort(key=lambda x: x['xymd'])
        
        result = "PENDING"
        
        # ---------------------------------------------------------
        # [채점 로직]
        # ---------------------------------------------------------
        
        # 1. 매수 (BUY) 채점
        if action == "BUY":
            for candle in future_candles:
                high = float(candle['high'])
                low = float(candle['low'])
                if low <= cut:
                    result = "LOSE" # 손절가 이탈
                    break 
                elif high >= target:
                    result = "WIN"  # 목표가 도달
                    break 

        # 2. 매도 (SELL) 채점
        elif action == "SELL":
            for candle in future_candles:
                high = float(candle['high'])
                low = float(candle['low'])
                if high >= cut:
                    result = "LOSE" # 숏 손절
                    break
                elif low <= target:
                    result = "WIN"  # 숏 익절
                    break

        # 3. 관망 (HOLD/WAIT) 채점 [신규]
        elif action in ["HOLD", "WAIT"]:
            # 기준: 진입가 대비 5% 이상 오르면 "아깝다(LOSE)"
            # 기준: 3일(영업일 기준 아님, 단순 경과일) 지났는데 별거 없으면 "잘참았다(WIN)"
            
            opportunity_threshold = entry_price * 1.05 # +5% 급등 기준
            days_passed = (today - entry_date.date()).days
            
            has_risen = False
            for candle in future_candles:
                high = float(candle['high'])
                if high >= opportunity_threshold:
                    result = "LOSE" # 관망하랬는데 떡상함 (기회 놓침)
                    has_risen = True
                    break
            
            # 급등한 적이 없고, 시간이 충분히 흘렀다면 방어 성공으로 간주
            if not has_risen:
                if days_passed >= 3:
                    result = "WIN" # 3일간 큰 상승 없었음 (방어 성공)
                else:
                    result = "PENDING" # 아직 지켜보는 중

        # ---------------------------------------------------------
        
        if result != "PENDING":
            print(f" -> [결과확정] {ticker} ({action}): {result}")
            mervis_bigquery.update_trade_result(ticker, entry_date, result)
            
            if result == "WIN": count_win += 1
            else: count_lose += 1
        else:
            count_pending += 1

    print("-" * 60)
    print(f" [채점 완료] WIN: {count_win} | LOSE: {count_lose} | PENDING: {count_pending}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_examination()