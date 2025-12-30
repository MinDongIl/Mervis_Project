import yfinance as yf
import datetime

def get_stock_news(ticker):
    try:
        # yfinance Ticker 객체 생성
        stock = yf.Ticker(ticker)
        news_list = stock.news
        
        if not news_list:
            return " [News] 해당 종목의 최신 뉴스를 찾을 수 없습니다."

        summary = []
        summary.append(f"=== [{ticker}] Latest News Analysis ===")
        
        # 최신 뉴스 5개만 추출
        for item in news_list[:5]:
            title = item.get('title', 'No Title')
            # link = item.get('link', '') # 필요 시 링크 포함
            # 시간 처리는 복잡할 수 있으므로 생략하거나 단순화
            summary.append(f"- {title}")
            
        return "\n".join(summary)

    except Exception as e:
        return f" [News Error] 뉴스 데이터 수집 실패: {e}"