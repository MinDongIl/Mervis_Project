# MERVIS Project: Intelligent Stock Investment Partner & Cloud-Native Platform

**Mervis(머비스)**는 Google Gemini API의 강력한 추론 능력, Google BigQuery의 영구적인 기억 저장소, 그리고 실시간 뉴스 분석 능력을 결합한 '자율 성장형 AI 주식 투자 파트너'입니다.

단순히 지표를 보고 매매하는 봇이 아닙니다. 머비스는 사용자의 투자 성향을 클라우드에 기록하고, 과거의 수만 가지 매매 데이터를 기반으로 자신의 실력을 스스로 검증하며 진화하는 하나의 인격체(Persona)입니다. 최근 클라우드 네이티브(Cloud-Native) 환경으로 아키텍처를 확장하여, 고가용성 웹 서빙과 무중단 배포(CI/CD)를 지원합니다.

---

## Who is Mervis?

**"데이터 기반의 냉철한 분석가이자, 당신의 성장을 돕는 파트너"**

머비스는 단순한 도구가 아닌 파트너로서 다음 역할을 수행합니다:

1.  **The Strategist (전략가):** 차트의 기술적 분석(Technical)뿐만 아니라, 수급(Supply) 및 기본적 분석(Fundamental), 뉴스(Material)를 결합하여 매수/매도/관망 전략을 수립합니다.
2.  **The Sniper (저격수):** 전체 시장을 스캔하다가도, 사용자가 지목한 타겟 종목을 즉시 포착하여 심층 분석 보고서를 제출합니다.
3.  **The Learner (학습자):** 자신의 모든 분석 리포트와 결과를 BigQuery에 적재합니다. 과거의 판단을 되돌아보고 승률을 스스로 계산하여 학습합니다.
4.  **The Profiler (프로파일러):** 사용자와의 대화를 통해 투자 성향(공격형/안정형)을 파악하고, 클라우드에 저장된 프로필을 바탕으로 맞춤형 조언을 제공합니다.

---

## Key Features

### 1. Cloud Memory System (Google BigQuery)
- **Infinite Storage:** 파일 용량 걱정 없이 수십 년 치의 매매 기록과 대화 로그를 저장합니다.
- **Self-Correction:** 과거에 자신이 내린 판단과 실제 주가 흐름을 비교하여, 예측 정확도를 스스로 검증하고 데이터화합니다.

### 2. Hybrid Analysis System & Modularization
- **3-Tier Analysis:** 기술적(Technical), 기본적(Fundamental), 수급(Supply) 분석 모듈을 독립적으로 구성하여 분석의 깊이와 확장성을 확보했습니다.
- **Real + Mock:** '실전 투자(Real)' 서버의 풍부한 데이터를 사용하여 분석의 정확도를 높이고, '모의 투자(Mock)' 서버를 사용하여 리스크 없이 전략을 검증합니다.

### 3. Smart News & Data Integration
- **Google News RSS Engine:** 외부 라이브러리 의존도를 낮추고, Google News RSS를 직접 수집하여 정확한 최신 뉴스 헤드라인을 분석에 반영합니다.
- **Volume Fallback Logic:** 무료 API 환경에서 실시간 거래량 데이터가 제공되지 않을 경우, 전일 종가 기준 거래량을 자동으로 참조하여 유동성 분석을 수행합니다.

### 4. Cloud-Native & DevOps Ready
- **Web Serving (`app.py`):** Flask 기반의 웹훅 및 Health Check 엔드포인트를 제공하여 GCP 로드밸런서 및 오토스케일링 인프라와 완벽하게 연동됩니다.
- **CI/CD Pipeline:** `cloudbuild.yaml`과 `Dockerfile`을 통해 코드가 푸시되면 자동으로 컨테이너 이미지를 빌드하고 무중단 배포(Rolling Update)를 수행합니다.

### 5. Interactive GUI & Consultation
- **Desktop Application (`main_gui.py`):** 차트 뷰, 채팅 뷰, 주식 뷰 등 직관적인 UI 위젯을 통해 사용자와 상호작용합니다.
- **Personalization:** 사용자의 대화 패턴을 분석하여 성향을 정의하고, 어떤 환경에서 실행하더라도 일관된 맞춤형 조언을 제공합니다.

---

## Project Structure

```bash
Mervis_Project/
├── app.py                  # [Web] 웹 서빙 및 상태 검사(Health Check) 엔드포인트
├── main.py                 # [CLI] 시스템 메인 엔트리 (스캔/스나이퍼/대화)
├── main_gui.py             # [GUI] 데스크톱 애플리케이션 메인
├── ui_widgets/             # [GUI] 화면 구성 요소 모듈 (Chat, Chart, Stock)
├── modules/                # [Core] 핵심 분석 모듈 (fundamental, supply, technical)
├── mervis_brain.py         # [AI] Gemini API 프롬프트 및 판단 로직
├── mervis_ai.py            # [AI] 사용자 상담 인터페이스 (Consulting)
├── mervis_bigquery.py      # [DB] 구글 BigQuery 연동 (기억/프로필 저장)
├── mervis_news.py          # [Data] 구글 뉴스 RSS 수집 엔진
├── mervis_profile.py       # [User] 사용자 성향 분석 및 관리
├── mervis_state.py         # [System] 시스템 상태 관리 (Real/Mock 모드)
├── mervis_server_manager.py # [System] 서버 모니터링 및 상태 관리
├── kis_*.py                # [API] 한국투자증권 Open API 연동 모듈 모음
├── notification.py         # [Alert] Discord 외부 알림 발송 모듈
├── Dockerfile              # [DevOps] 컨테이너 이미지 빌드 명세서
├── cloudbuild.yaml         # [DevOps] GCP Cloud Build CI/CD 파이프라인
└── journal/                # 개발 및 연구 일지 보관소
```

---

## Tech Stack

```text
* Language: Python 3.11+
* AI Engine: Google GenAI SDK (Gemini 2.0 Flash - Paid Plan)
* Database: Google BigQuery (Serverless Data Warehouse)
* Data Source: Korea Investment Securities (KIS) Open API, Google News RSS
* Web/GUI: Flask, PyQt/PySide (UI Widgets)
* DevOps/Cloud: Docker, Google Cloud Build, Google Compute Engine (MIG)
* Observability: Discord Webhook 연동 (notification.py)
```

---

## Disclaimer

이 프로젝트는 개인의 투자 연구 및 AI 학습을 목적으로 개발되었습니다. 머비스(Mervis)가 제공하는 분석 리포트는 AI의 추론일 뿐이며, 실제 투자의 모든 책임은 사용자 본인에게 있습니다. API 사용 시 발생하는 과금(Cloud 비용 등)이나 매매 손실에 대해 개발자는 책임지지 않습니다.