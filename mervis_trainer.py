import sys
import logging
from google.cloud import bigquery
import mervis_bigquery

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [TRAINER] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def run_training():
    """
    [AI 모델 재학습]
    라벨링(수익률 계산)이 완료된 데이터를 사용하여
    'Boosted Tree Regressor' 모델을 새로 학습시킵니다.
    """
    client = mervis_bigquery.get_client()
    if not client:
        logging.error("BigQuery 클라이언트 연결 실패")
        return

    logging.info(">>> 머신러닝 모델 재학습(Retraining) 시작...")

    # [모델 학습 쿼리]
    # CREATE OR REPLACE MODEL: 기존 모델을 덮어쓰기
    # model_type='BOOSTED_TREE_REGRESSOR': 정형 데이터(표) 학습에 강력한 모델 (XGBoost 계열)
    query = f"""
        CREATE OR REPLACE MODEL `{client.project}.{mervis_bigquery.DATASET_ID}.return_forecast_model`
        OPTIONS(
            model_type = 'BOOSTED_TREE_REGRESSOR',
            input_label_cols = ['next_day_return'], -- AI가 맞춰야 할 정답
            max_iterations = 50,  -- 학습 반복 횟수
            learn_rate = 0.3      -- 학습률
        ) AS
        SELECT
            -- [학습할 문제들 Features]
            -- 기술적 지표
            rsi, 
            vwap_ratio, 
            ma20_ratio, 
            vol_ratio,
            
            -- 펀더멘털
            forward_pe, 
            target_upside,
            
            -- 수급 (중요)
            inst_pct, 
            short_ratio,
            
            -- [정답 Label]
            next_day_return
            
        FROM `{client.project}.{mervis_bigquery.DATASET_ID}.{mervis_bigquery.TABLE_FEATURES}`
        WHERE
            -- 정답이 있는 데이터만 학습
            next_day_return IS NOT NULL
            -- 최근 2년치 데이터만 사용 (시장 트렌드 반영)
            AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 YEAR)
    """

    try:
        # 학습은 데이터 양에 따라 시간이 좀 걸릴 수 있음 (수십 초 ~ 수 분)
        query_job = client.query(query)
        query_job.result()
        logging.info("<<< 모델 학습 완료. 새로운 모델이 배포되었습니다.")
        
        # (선택) 학습 결과 평가
        eval_query = f"""
            SELECT * FROM ML.EVALUATE(MODEL `{client.project}.{mervis_bigquery.DATASET_ID}.return_forecast_model`)
        """
        eval_job = client.query(eval_query)
        metrics = list(eval_job.result())[0]
        logging.info(f"    [모델 성능] Mean Absolute Error: {metrics.mean_absolute_error:.5f}")
        
    except Exception as e:
        logging.error(f"모델 학습 중 오류: {e}")

if __name__ == "__main__":
    run_training()