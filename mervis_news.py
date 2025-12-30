import requests
import xml.etree.ElementTree as ET
import urllib.parse

def get_stock_news(ticker):
    """
    구글 뉴스 RSS를 통해 해당 종목의 최신 뉴스(영어/한국어 혼합)를 가져옵니다.
    """
    try:
        # 검색어 인코딩 (예: MU stock)
        query = urllib.parse.quote(f"{ticker} stock")
        
        # 구글 뉴스 RSS URL (미국 주식 기준, 최신순)
        # hl=en-US: 영어권 뉴스 우선 (미국 주식이므로)
        url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"
        
        # 데이터 요청 (타임아웃 5초 설정)
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            return f" [News Error] 구글 뉴스 접속 실패 (Code: {response.status_code})"

        # XML 파싱
        root = ET.fromstring(response.content)
        
        summary = []
        summary.append(f"=== [{ticker}] Latest Google News (RSS) ===")
        
        count = 0
        # XML 구조: channel -> item -> title/pubDate
        for item in root.findall('./channel/item'):
            if count >= 5: break # 5개까지만
            
            title = item.find('title').text
            pub_date = item.find('pubDate').text
            
            # 제목에 종목명이나 관련 키워드가 있는지 약식 체크 (옵션)
            summary.append(f"- {title} ({pub_date})")
            count += 1
            
        if count == 0:
            return " [News] 최근 7일간 검색된 관련 뉴스가 없습니다."
            
        return "\n".join(summary)

    except Exception as e:
        return f" [News System Error] 뉴스 처리 중 오류: {e}"