# MERVIS Project: Intelligent US Stock Investment Partner

**Mervis(머비스)**는 Google Gemini API의 강력한 추론 능력과 Google BigQuery의 영구적인 기억 저장소, 그리고 실시간 뉴스 분석 능력을 결합한 '자율 성장형 AI 주식 투자 파트너'입니다.

단순히 지표를 보고 매매하는 봇이 아닙니다. 머비스는 사용자의 투자 성향을 클라우드에 기록하고, 과거의 수만 가지 매매 데이터를 기반으로 자신의 실력을 스스로 검증하며 진화하는 하나의 인격체(Persona)입니다.

---

## Who is Mervis?

**"데이터 기반의 냉철한 분석가이자, 당신의 성장을 돕는 파트너"**

머비스는 단순한 도구가 아닌 파트너로서 다음 역할을 수행합니다:

1.  **The Strategist (전략가):** 차트의 기술적 분석(Price Action)뿐만 아니라, 뉴스(Material)를 결합하여 매수/매도/관망 전략을 수립합니다.
2.  **The Sniper (저격수):** 전체 시장을 스캔하다가도, 사용자가 지목한 타겟 종목을 즉시 포착하여 심층 분석 보고서를 제출합니다.
3.  **The Learner (학습자):** 자신의 모든 분석 리포트와 결과를 BigQuery에 적재합니다. 과거의 판단을 되돌아보고 승률을 스스로 계산하여 학습합니다.
4.  **The Profiler (프로파일러):** 사용자와의 대화를 통해 투자 성향(공격형/안정형)을 파악하고, 클라우드에 저장된 프로필을 바탕으로 맞춤형 조언을 제공합니다.

---

## Key Features

### 1. Cloud Memory System (Google BigQuery)
- **Infinite Storage:** 파일 용량 걱정 없이 수십 년 치의 매매 기록과 대화 로그를 저장합니다.
- **Self-Correction:** 과거에 자신이 내린 판단과 실제 주가 흐름을 비교하여, 예측 정확도를 스스로 검증하고 데이터화합니다.

### 2. Sniper Search Mode (On-Demand Analysis)
- 시장 스캔 리스트에 없는 종목이라도 사용자가 티커를 입력하는 즉시 API를 호출하여 분석합니다.
- 실시간 차트 데이터와 뉴스 데이터를 결합하여 즉각적인 전략을 수립합니다.

### 3. Smart News Integration
- **Google News RSS Engine:** 외부 라이브러리 의존도를 낮추고, Google News RSS를 직접 수집하여 정확한 최신 뉴스 헤드라인을 분석에 반영합니다.
- 단순한 차트 분석을 넘어 시장의 재료(Issue)를 해석합니다.

### 4. Volume Fallback Logic
- 무료 API 환경에서 실시간 거래량 데이터가 제공되지 않을 경우, 전일 종가 기준 거래량을 자동으로 참조하여 유동성 분석을 수행합니다.

### 5. User Personalization (Profile)
- 사용자의 대화 패턴과 요구사항을 분석하여 성향을 정의하고 BigQuery에 저장합니다.
- 어떤 환경에서 실행하더라도 사용자의 투자 스타일을 기억하고 일관된 조언을 제공합니다.

---

## Key Features

### 1. Hybrid Investment System (Real + Mock)
- **데이터 조회:** '실전 투자(Real)' 서버의 풍부한 데이터를 사용하여 분석의 정확도를 높입니다.
- **주문 실행:** '모의 투자(Mock)' 서버를 사용하여 리스크 없이 전략을 검증하고 실력을 쌓습니다.

### 2. Full Market Scanning (Dynamic Trend)
- 특정 종목만 편식하지 않습니다.
- 시장 상황(개장/휴장)을 자동 감지하고, 현재 시장을 주도하는 **거래량 상위 / 상승률 상위** 종목을 실시간으로 채굴하여 분석합니다.

### 3. Self-Learning Loop (Memory)
- **Memory:** 분석한 모든 종목의 리포트를 기억합니다.
- **Feedback:** "어제 내가 추천한 종목이 올랐는가?"를 스스로 확인하고, 틀렸다면 그 원인을 분석하여 다음 프롬프트(두뇌)에 반영합니다.

### 4. High-Performance Brain
- **Core:** Google Gemini 2.0 Flash (Paid Plan)
- **Speed:** API 속도 제한 없이 초고속으로 대량의 종목을 분석하고 대응합니다.

---

## Project Structure

```bash
Mervis_Project/
├── main.py             # 시스템 엔트리 (메뉴: 스캔 / 스나이퍼 / 대화)
├── mervis_brain.py     # [Core] AI 두뇌 (Gemini + 프롬프트 + 판단 로직)
├── mervis_bigquery.py  # [New] 구글 클라우드 DB 연동 (기억/프로필 저장)
├── mervis_news.py      # [New] 구글 뉴스 RSS 수집 엔진
├── mervis_profile.py   # 사용자 성향 분석 및 관리 (BigQuery 연동)
├── mervis_ai.py        # 사용자 상담 인터페이스 (Consulting)
├── mervis_state.py     # 시스템 상태 관리 (Real/Mock 모드)
├── kis_scan.py         # 시장 스캐너 (동적 타겟팅)
├── kis_chart.py        # 차트 데이터 전처리 및 보조지표 산출
├── kis_auth.py         # KIS API 토큰 관리 (Auto Refresh)
├── service_account.json # [Security] GCP 인증 키 (Git 업로드 절대 금지)
└── journal/            # 개발 및 연구 일지 (History)
```

### 2. Tech Stack (기술 스택)

```text
* **Language:** Python 3.11+
* **AI Engine:** Google GenAI SDK (Gemini)
* **Database:** Google BigQuery (Serverless Data Warehouse)
* **Data Source:** Korea Investment Securities (KIS) Open API, Google News RSS (XML Parsing)
* **Libraries:** google-genai, google-cloud-bigquery, pandas, requests
```

## Disclaimer

이 프로젝트는 개인의 투자 연구 및 AI 학습을 목적으로 개발되었습니다. 머비스(Mervis)가 제공하는 분석 리포트는 AI의 추론일 뿐이며, 실제 투자의 모든 책임은 사용자 본인에게 있습니다. API 사용 시 발생하는 과금(Cloud 비용 등)이나 매매 손실에 대해 개발자는 책임지지 않습니다.
