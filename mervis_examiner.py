import mervis_bigquery
import kis_chart
import datetime
import mervis_state
from google import genai
import secret
import os

# Gemini 클라이언트 설정 (반성문 작성용)
client = genai.Client(api_key=secret.GEMINI_API_KEY)

# 1일 1회 실행 제한을 위한 타임스탬프 파일 설정
TIMESTAMP_FILE = ".examiner_last_run"

def check_if_already_run():
    """오늘 이미 채점을 수행했는지 확인"""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(TIMESTAMP_FILE):
        try:
            with open(TIMESTAMP_FILE, "r") as f:
                last_run = f.read().strip()
            if last_run == today_str:
                return True # 이미 실행함
        except:
            return False
            
    return False

def mark_as_run():
    """오늘 실행했다고 기록"""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        with open(TIMESTAMP_FILE, "w") as f:
            f.write(today_str)
    except: pass

def generate_feedback(item):
    """
    [AI] 매매 결과에 대한 원인 분석 및 교훈 도출
    """
    try:
        # PENDING은 분석 대상 아님
        if item['result'] not in ['WIN', 'LOSE']:
            return None

        prompt = f"""
        You are a strict trading coach. Analyze the following trade result.
        
        [Trade Info]
        - Ticker: {item['ticker']}
        - Action: {item['action']}
        - Entry Price: ${item['entry_price']}
        - Result: {item['result']} (WIN = Success, LOSE = Failed)
        - Original Analysis Summary: {item['report'][:500]}...
        
        [Task]
        Write a very short, brutal "Lesson Learned" (One sentence, Korean).
        If LOSE: Why did the analysis fail? (e.g., "Ignored macro trend", "RSI was misleading")
        If WIN: Why did it succeed? (e.g., "Good catch on volume spike")
        
        Output example:
        "하락장에서는 과매도 시그널도 무시하고 관망했어야 함."
        """
        
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"피드백 생성 실패: {e}"

def run_examination():
    """
    [채점관 실행]
    Phase 1: 채점 (WIN/LOSE 판정)
    Phase 2: 피드백 (오답노트 작성)
    """
    
    # 오늘 이미 실행했는지 체크
    if check_if_already_run():
        print(" [Examiner] 오늘의 자기 복기(채점)가 이미 완료되었습니다. (Skip)")
        return

    print("\n" + "="*60)
    print(" [Examiner] 자기 복기 시스템 (채점 및 심층 분석)")
    print("="*60)
    
    # 데이터 정합성을 위해 실전 모드
    mervis_state.set_mode("REAL")
    
    # ---------------------------------------------------------
    # Phase 1: 채점 (Grading)
    # ---------------------------------------------------------
    pending_list = mervis_bigquery.get_pending_trades()
    
    if not pending_list:
        print(" [Grading] 채점할 대기 목록이 없습니다.")
    else:
        print(f" [Grading] 총 {len(pending_list)}건의 검증 대기 항목 채점 시작...")
        
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
            
            start_date_str = entry_date.strftime("%Y%m%d")
            daily_chart = kis_chart.get_daily_chart(ticker)
            
            if not daily_chart:
                print(f" -> [Skip] {ticker}: 차트 데이터 조회 실패")
                continue
                
            future_candles = []
            for candle in daily_chart:
                if candle['xymd'] >= start_date_str:
                    future_candles.append(candle)
            future_candles.sort(key=lambda x: x['xymd'])
            
            result = "PENDING"
            
            # 1. 매수 (BUY) 채점
            if action == "BUY":
                for candle in future_candles:
                    h, l = float(candle['high']), float(candle['low'])
                    if l <= cut:
                        result = "LOSE"
                        break 
                    elif h >= target:
                        result = "WIN"
                        break 

            # 2. 매도 (SELL) 채점
            elif action == "SELL":
                for candle in future_candles:
                    h, l = float(candle['high']), float(candle['low'])
                    if h >= cut:
                        result = "LOSE"
                        break
                    elif l <= target:
                        result = "WIN"
                        break

            # 3. 관망 (HOLD/WAIT) 채점
            elif action in ["HOLD", "WAIT"]:
                opportunity_threshold = entry_price * 1.05
                days_passed = (today - entry_date.date()).days
                
                has_risen = False
                for candle in future_candles:
                    if float(candle['high']) >= opportunity_threshold:
                        result = "LOSE" # 기회 놓침
                        has_risen = True
                        break
                
                if not has_risen:
                    if days_passed >= 3:
                        result = "WIN" # 방어 성공
                    else:
                        result = "PENDING"

            if result != "PENDING":
                print(f" -> [결과확정] {ticker} ({action}): {result}")
                mervis_bigquery.update_trade_result(ticker, entry_date, result)
                
                if result == "WIN": count_win += 1
                else: count_lose += 1
            else:
                count_pending += 1

        print(f" [Grading 완료] WIN: {count_win} | LOSE: {count_lose} | PENDING: {count_pending}")

    # ---------------------------------------------------------
    # Phase 2: 오답노트 작성 (Feedback Loop)
    # ---------------------------------------------------------
    print("-" * 60)
    print(" [Review] 오답노트 작성(피드백 생성) 시작...")
    
    # 채점은 됐는데 피드백이 없는 항목 조회
    review_list = mervis_bigquery.get_trades_needing_feedback()
    
    if not review_list:
        print(" -> 작성할 오답노트가 없습니다.")
    else:
        for item in review_list:
            print(f" -> [{item['ticker']}] ({item['result']}) 원인 분석 중...", end="")
            feedback = generate_feedback(item)
            if feedback:
                mervis_bigquery.update_trade_feedback(item['ticker'], item['date'], feedback)
                print(f" 완료.\n    교훈: {feedback}")
            else:
                print(" 실패.")
    
    # 실행 완료 기록
    mark_as_run()
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_examination()