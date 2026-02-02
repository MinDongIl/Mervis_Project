import sys
import logging
from google.cloud import bigquery
import mervis_bigquery  # 인증 정보 재사용

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [LABELER] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def run_labeling():
    """
    [데이터 정답지 생성]
    daily_features 테이블에 있는 데이터 중, 
    아직 수익률(next_day_return)이 비어있는 행을 찾아
    '다음 날 종가'를 기준으로 수익률을 계산하여 업데이트.
    """
    client = mervis_bigquery.get_client()
    if not client:
        logging.error("BigQuery 클라이언트 연결 실패")
        return

    logging.info(">>> 데이터 라벨링(채점) 작업 시작...")

    # MERGE문을 사용, 같은 종목(ticker)의 다음 날짜(LEAD) 가격을 가져와 수익률 계산
    # 주말/휴일 건너뛰고 바로 다음 거래일 데이터를 가져옴
    query = f"""
        MERGE `{client.project}.{mervis_bigquery.DATASET_ID}.{mervis_bigquery.TABLE_FEATURES}` T
        USING (
            SELECT 
                date, 
                ticker,
                -- 같은 종목 내에서 날짜순으로 정렬했을 때, 바로 다음 행의 가격(next_price)을 가져옴
                LEAD(price) OVER (PARTITION BY ticker ORDER BY date ASC) as next_price
            FROM `{client.project}.{mervis_bigquery.DATASET_ID}.{mervis_bigquery.TABLE_FEATURES}`
        ) S
        ON T.ticker = S.ticker AND T.date = S.date
        -- 조건: 아직 정답(수익률)이 없고, 다음 날 가격(S.next_price)이 존재할 때만 업데이트
        WHEN MATCHED AND T.next_day_return IS NULL AND S.next_price IS NOT NULL THEN
            UPDATE SET next_day_return = (S.next_price - T.price) / T.price
    """

    try:
        query_job = client.query(query)
        query_job.result()  # 쿼리 완료 대기
        
        # 업데이트된 행 수 확인 (query_job.num_dml_affected_rows)
        logging.info(f"<<< 라벨링 완료. (업데이트된 데이터: {query_job.num_dml_affected_rows}건)")
        
    except Exception as e:
        logging.error(f"라벨링 쿼리 실행 중 오류: {e}")

if __name__ == "__main__":
    run_labeling()