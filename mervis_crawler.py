import time
import logging
from datetime import datetime
from google.cloud import bigquery

# 사용자 모듈 임포트
import mervis_bigquery
import kis_chart
from modules import technical, fundamental, supply

# 로깅 설정 (파일로 기록 남김)
logging.basicConfig(
    filename='crawler.log', 
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def get_all_tickers():
    """
    BigQuery에서 전체 종목 리스트를 가져옴 (status 상관없이 전체 스캔)
    """
    client = mervis_bigquery.get_client()
    if not client: return []
    
    # TABLE_TICKERS 테이블에서 모든 ticker 조회
    query = f"""
        SELECT ticker 
        FROM `{client.project}.{mervis_bigquery.DATASET_ID}.{mervis_bigquery.TABLE_TICKERS}`
    """
    try:
        results = list(client.query(query).result())
        return [row.ticker for row in results]
    except Exception as e:
        print(f" [Crawler] 종목 리스트 로드 실패: {e}")
        logging.error(f"Failed to load tickers: {e}")
        return []

def run_night_crawler():
    print(" [Crawler] 야간 자율 주행 시작... (전체 종목 스캔)")
    tickers = get_all_tickers()
    
    if not tickers:
        print(" [Crawler] 스캔할 종목이 없습니다.")
        return

    total = len(tickers)
    print(f" [Crawler] 총 {total}개 종목 분석 예정.")
    
    success_count = 0
    fail_count = 0

    for idx, ticker in enumerate(tickers):
        try:
            # 진행률 표시
            if idx % 10 == 0:
                print(f" Progress: {idx}/{total} ({success_count} Success, {fail_count} Fail)")
            
            # 1. 차트 데이터 수집 (KIS API)
            # 기술적 지표 계산을 위해 일봉 데이터 필요
            d_data = kis_chart.get_daily_chart(ticker)
            if not d_data or len(d_data) < 20:
                fail_count += 1
                continue

            # 2. 모듈별 분석 실행
            
            # A. Technical (이격도, 거래량 비율, RSI 등 추출)
            # 전략 리스트는 비워둠 (지표 추출이 목적)
            tech_data, _, _ = technical.analyze_technical_signals(d_data, [])
            
            # B. Supply (기관 비중, 공매도 비율 추출)
            # yfinance 사용
            supply_data, supply_err, _ = supply.analyze_supply_structure(ticker)
            if supply_err: 
                # 수급 데이터가 없어도 기술적 데이터는 있으므로 진행은 함 (로그만 기록)
                logging.warning(f"{ticker} Supply Error: {supply_err}")

            # C. Fundamental (PER, 컨센서스 추출)
            # yfinance 사용
            fund_data, fund_err, _ = fundamental.analyze_fundamentals(ticker)
            if fund_err:
                logging.warning(f"{ticker} Fund Error: {fund_err}")

            # 3. 데이터 마트(BigQuery)에 저장
            mervis_bigquery.save_daily_features(ticker, tech_data, fund_data, supply_data)
            
            success_count += 1
            logging.info(f"Saved features for {ticker}")

            # 4. Rate Limiting (중요)
            # KIS API 및 yfinance 차단 방지를 위해 딜레이 부여
            time.sleep(1.5) 

        except Exception as e:
            fail_count += 1
            logging.error(f"Error processing {ticker}: {e}")
            print(f" [Error] {ticker}: {e}")
            time.sleep(5) # 에러 발생 시 잠시 대기

    print(f" [Crawler] 작업 완료. 성공: {success_count}, 실패: {fail_count}")

if __name__ == "__main__":
    # 단독 실행 시 크롤러 가동
    run_night_crawler()