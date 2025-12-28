import yfinance as yf

def get_realtime_rate():
    """
    실시간 원/달러 환율 조회 (Yahoo Finance 기반)
    """
    try:
        ticker = yf.Ticker("KRW=X")
        data = ticker.history(period="1d")
        rate = data['Close'].iloc[-1]
        print(f"머비스: 실시간 환율 확인 완료 (1$ = {rate:.2f}원)")
        return rate
    except Exception as e:
        print(f"머비스: 환율 조회 실패, 비상용 고정 환율(1450) 사용. ({e})")
        return 1450.0

if __name__ == "__main__":
    get_realtime_rate()