# MERVIS Project: Intelligent US Stock Investment Partner

**Mervis(머비스)**는 Google Gemini API의 강력한 추론 능력과 한국투자증권(KIS)의 실전 데이터를 결합한 **'자율 성장형 AI 주식 투자 파트너'**입니다.

단순한 자동매매 봇이 아닙니다. 머비스는 시장 상황을 스스로 판단하고, 과거의 분석을 기억하며, 끊임없이 자신의 예측을 검증하고 성장하는 **인격체(Persona)**를 지향합니다.

---

## Who is Mervis?

**"냉철한 데이터 분석가이자, 당신의 성장을 돕는 독설가 파트너"**

머비스는 사용자의 주식 투자를 보조하기 위해 다음과 같은 역할을 수행합니다:

1.  **The Analyst (분석가):** NASDAQ/NYSE 전 종목을 스캔하여 트렌드(급등, 거래량 폭발)를 포착하고, 기술적 분석(Trend, Support, Resistance)을 수행합니다.
2.  **The Manager (관리자):** 장이 열려 있을 때는 실시간 대응 전략을, 장이 닫혀 있을 때는 직전 장 복기를 통해 미래 시나리오를 설계합니다.
3.  **The Learner (학습자):** 자신의 분석 결과를 DB(mervis_history.json)에 저장하고, 다음 분석 시 과거의 예측이 맞았는지 스스로 검증(Self-Feedback)하여 전략을 수정합니다.
4.  **The Strict Coach (코치):** 무지성 매매나 위험한 투자를 경계하며, 객관적인 팩트와 논리로 사용자의 멘탈을 관리합니다.

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
├── main.py             # 프로그램 진입점 (모드 선택 및 시스템 가동)
├── mervis_brain.py     # AI 두뇌 (Gemini 연동, 프롬프트 엔지니어링, 기억 관리)
├── mervis_ai.py        # 상담 인터페이스 (사용자와의 대화)
├── kis_scan.py         # 시장 스캐너 (트렌드 종목 발굴, 휴장 시 비상 로직)
├── kis_chart.py        # 차트 데이터 처리 및 보조지표 계산
├── kis_auth.py         # 인증 토큰 관리 (디스크 캐싱 적용)
├── kis_order.py        # 주문 집행 (매수/매도)
├── secret.py           # (보안) API Key 및 계좌 정보 *Git 업로드 금지*
└── journal/            # 개발 및 연구 일지 (History)
```

### 2. Tech Stack (기술 스택)

```text
* **Language:** Python 3.11+
* **AI Engine:** Google GenAI SDK (Gemini)
* **Data Provider:** Korea Investment Securities (KIS) Open API
* **Data Processing:** Pandas
```

## Disclaimer

이 프로젝트는 개인의 투자 연구 및 학습을 위해 개발되었습니다.
머비스(Mervis)가 제공하는 분석 정보는 투자의 참고 자료일 뿐이며, **모든 투자의 책임은 사용자 본인에게 있습니다.**
