from google import genai
import os
import mervis_profile 
import mervis_bigquery 
import mervis_brain
import kis_websocket
import json
import re

# API 키를 환경 변수에서 로드
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
USER_NAME = os.getenv("USER_NAME", "User")

# --- GUI 연동용 AI 엔진 클래스 ---
class MervisAI_Engine:
    def __init__(self):
        self.history = []
        self.last_ticker = None
        self.last_report = ""
        self.last_price = 0.0
        
        # 시스템 프롬프트 준비
        user_data = mervis_profile.get_user_profile()
        profile_str = json.dumps(user_data, indent=2, ensure_ascii=False)
        
        self.system_instruction = f"""
        당신은 사용자의 냉철한 주식 비서 '머비스(Mervis)'입니다.
        
        [절대 원칙]
        1. 이모티콘을 절대 사용하지 마십시오.
        2. 말투: {USER_NAME}에게 똑똑하고 주관 뚜렷한 친구처럼 '반말'로 직설적으로 조언하라.
        3. [Context]에 없는 내용은 절대 지어내지 마십시오. 모르면 "데이터가 없습니다"라고 하십시오.
        4. 사용자가 "알림"이나 "감시"를 요청하면, 시스템 로그를 확인하여 실제로 설정되었는지 보고 말하십시오.
           - 실패했으면 "설정 실패했다"고 솔직히 말하고 이유를 대십시오.
           - 성공했으면 "설정 완료했다"고 확인해 주십시오.
        
        [User Profile]
        {profile_str}
        """

    def get_response(self, user_input):
        """
        사용자 입력을 받아 처리 후 답변 반환 (GUI용)
        """
        if not user_input: return ""

        injected_context = ""
        
        # 1. 종목 분석 요청 감지
        potential_tickers = re.findall(r'\b[A-Z]{2,5}\b', user_input.upper())
        # 한글 종목명 매핑 로직이 있다면 여기서 변환 필요 (현재는 티커 기준)
        
        if potential_tickers:
            unique_tickers = list(set(potential_tickers))
            self.last_ticker = unique_tickers[-1]
            
            for t in unique_tickers:
                # Brain 분석 호출
                res = mervis_brain.analyze_stock({'code': t, 'name': t, 'price': 0})
                if res:
                    self.last_report = res['report']
                    self.last_price = res.get('price', 0)
                    injected_context += f"\n[Analysis Data for {t}]\n{self.last_report}\n"

        # 2. 알림/감시 요청 감지
        alert_keywords = ["알림", "알려줘", "감시", "오르면", "내리면", "도달", "되면", "손절", "목표", "전략"]
        if any(k in user_input for k in alert_keywords):
            
            # (A) 전략 기반 일괄 등록
            if "전략" in user_input or "그대로" in user_input:
                if self.last_ticker and self.last_report:
                    if _register_strategy_alert(self.last_ticker, self.last_report):
                        injected_context += f"\n[System Action] SUCCESS: {self.last_ticker}의 전략(진입/목표/손절) 알림을 모두 등록했습니다.\n"
                    else:
                        injected_context += "\n[System Action] FAILED: 리포트에서 가격 정보를 찾을 수 없습니다.\n"
                else:
                    injected_context += "\n[System Action] FAILED: 이전 분석 내역이 없습니다. 먼저 종목을 분석해 주세요.\n"

            # (B) 개별 가격 수동 등록
            else:
                params = _extract_alert_params(user_input, self.last_ticker, self.last_price)
                if params:
                    ticker = params['ticker'].upper()
                    price = params['price']
                    cond = params['condition']
                    
                    kis_websocket.add_watch_condition(ticker, price, cond, "사용자지정")
                    injected_context += f"\n[System Action] SUCCESS: 알림 설정 완료. 종목: {ticker}, 가격: ${price}, 조건: {cond}\n"
                    self.last_ticker = ticker
                else:
                    injected_context += f"\n[System Action] FAILED: 알림 설정 실패. 티커 또는 가격 불명확.\n"

        # 3. 추천 요청 감지
        recommend_keywords = ["추천", "종목 좀", "살만한거", "뭐 살까", "유망", "급등"]
        if any(k in user_input for k in recommend_keywords):
            rec_data = _get_recommendation_context(limit=3)
            injected_context += f"\n{rec_data}\n"

        # 4. 프롬프트 조립 및 요청
        full_prompt = f"{self.system_instruction}\n"
        
        # 최근 대화 4개만 포함
        for h in self.history[-4:]: full_prompt += f"{h}\n"
        
        if injected_context:
            full_prompt += f"\n[Injecting Real-time Data & Actions]\n{injected_context}\n"
        
        full_prompt += f"User: {user_input}\nMervis:"

        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt
            )
            answer = response.text.strip()
            
            # 대화 기록 저장
            self.history.append(f"User: {user_input}")
            self.history.append(f"Mervis: {answer}")
            
            # 사용자 프로필 업데이트 (긴 대화일 경우)
            if len(user_input) > 10:
                mervis_profile.update_user_profile(user_input)

            return answer

        except Exception as e:
            return f"[System Error] 응답 생성 실패: {e}"

# --- 기존 함수들 (헬퍼) ---

def _get_recommendation_context(limit=3):
    try:
        if hasattr(mervis_bigquery, 'get_top_ranked_stocks'):
            top_stocks = mervis_bigquery.get_top_ranked_stocks(limit)
        else:
            top_stocks = mervis_bigquery.get_tickers_from_db(limit)

        if not top_stocks:
            return " [System] 현재 DB에 분석된 추천 유망 종목이 없습니다."
            
        context = "[System Recommendation Data from DB]\n"
        for item in top_stocks:
            report = item.get('report', '상세 분석 데이터 없음')
            code = item.get('code')
            score = item.get('total_score', 0)
            context += f"- 종목명: {code} | 점수: {score}점 | 분석요약: {report}\n"
        return context
    except Exception as e:
        return f" [System Error] 추천 데이터 조회 실패: {e}"

def _register_strategy_alert(ticker, report_text):
    try:
        count = 0
        entry_match = re.search(r"진입가[:\s\$]+([\d\.]+)", report_text)
        if entry_match:
            price = float(entry_match.group(1))
            kis_websocket.add_watch_condition(ticker, price, "LE", "진입가")
            count += 1

        target_match = re.search(r"목표가[:\s\$]+([\d\.]+)", report_text)
        if target_match:
            price = float(target_match.group(1))
            kis_websocket.add_watch_condition(ticker, price, "GE", "목표가")
            count += 1

        cut_match = re.search(r"손절가[:\s\$]+([\d\.]+)", report_text)
        if cut_match:
            price = float(cut_match.group(1))
            kis_websocket.add_watch_condition(ticker, price, "LE", "손절가")
            count += 1
            
        return count > 0
    except Exception as e:
        print(f" [Debug] 전략 등록 오류: {e}")
        return False

def _extract_alert_params(user_input, last_ticker=None, current_price=None):
    try:
        text_upper = user_input.upper().replace(",", "")
        
        ticker_match = re.search(r'\b([A-Z]{2,5})\b', text_upper)
        ticker = ticker_match.group(1) if ticker_match else last_ticker
        
        if not ticker: return None
        
        price_match = re.search(r'(\d+(?:\.\d+)?)', text_upper)
        if not price_match: return None
        target_price = float(price_match.group(1))
        
        cond = None
        if any(x in text_upper for x in ["이상", "돌파", "오르", "넘으", "상승", "목표"]): cond = "GE"
        elif any(x in text_upper for x in ["이하", "이탈", "떨어", "내리", "하락", "손절"]): cond = "LE"
        
        if not cond and current_price and current_price > 0:
            if target_price > current_price: cond = "GE" 
            else: cond = "LE" 
        
        if not cond: cond = "GE"
            
        return {"ticker": ticker, "price": target_price, "condition": cond}

    except Exception as e:
        return None

# CLI용 (하위 호환)
def start_consulting(initial_context=""):
    engine = MervisAI_Engine()
    print("\n" + "="*40)
    print(" [MERVIS] Intelligent Chat Mode (Exit: q)")
    print("==================================================")
    
    while True:
        try:
            user_input = input("\n>> User: ").strip()
        except KeyboardInterrupt: return
        if user_input.lower() in ['q', 'exit']: return
        
        print(f"Mervis: {engine.get_response(user_input)}")