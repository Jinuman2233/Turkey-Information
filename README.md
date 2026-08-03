# 🇹🇷 터키 비즈니스 & 경제 동향 대시보드

터키 관련 사업/경제 정보를 한 화면에서 확인할 수 있는 **Streamlit** 기반 반응형 웹 대시보드입니다.
PC와 스마트폰 어디서든 보기 좋도록 반응형 레이아웃으로 만들어졌습니다.

## 주요 기능

1. **실시간 환율 카드** — EUR/TRY, USD/TRY, TRY/KRW 환율을 카드 형태로 크게 표시 (`yfinance` 사용)
   - 각 카드 아래에는 최근 3개월 환율 추이를 보여주는 미니 그래프가 함께 표시됩니다.
2. **터키 소비자물가지수(TÜİK TÜFE / CPI) 3년 장기 추이** — 터키 통계청(TÜİK) 공식 TÜFE를
   우선 수집해 YoY / MoM 지표 카드, 최근 12개월 MoM 표, 3년 복합 차트로 표시합니다.
   MESS ↔ Türk Metal 단체협약의 물가상승분(enflasyon farkı) 참고용으로 활용할 수 있습니다.
   API 실패 시에도 최신 공식 발표 흐름을 반영한 폴백 데이터를 사용합니다.
3. **터키 기준금리** — 최근 2년간 월별 기준금리를 라인 그래프로 표시 (`plotly` 사용)
4. **터키 최저임금** — 터키 노동부(CSGB) 등에서 **세전(Gross) Asgari Ücret**을 자동 수집
   - 월 최저임금(**Gross, 세전 기준**)과 현재 환율 기준 EUR / USD / KRW 환산 금액
   - 시간당 최저임금(**Gross, 세전 기준**, 월 근무시간 255시간 가정)과 EUR / USD / KRW 환산 금액
   - 카드 하단에 `적용/발표일: YYYY년 MM월` 표시 (실패 시 2026년 공식 기준 폴백)
5. **실시간 터키 뉴스 + AI 한국어 번역** — 무역·관세 / 이민·비자 / 노무·노동조합 / 물류·인프라 /
   외투기업·제조업 규제, 5가지 주제의 최신 뉴스를 구글 뉴스(Google News RSS)에서 자동 수집하고,
   **Google Gemini REST API**(`gemini-1.5-flash` → 실패 시 `gemini-1.5-flash-latest` → `gemini-pro`)를
   **SDK 없이 `requests`로 직접 호출**해 한국어 번역·요약까지 자동으로 처리합니다.
   - 메인 화면에는 번역된 **한국어 제목만** 깔끔한 리스트로 표시됩니다.
   - 제목을 클릭(`st.expander`)하면 한국어 3줄 요약과 **원문 기사 링크**(새 창으로 열림)가 펼쳐집니다.
   - API 키가 없거나 수집/번역에 실패하면, 레이아웃 확인용 예시(더미) 뉴스로 자동 대체됩니다.
   - API 호출이 실패하면(200이 아닌 응답) 원인을 바로 알 수 있도록 **실제 응답 원문을 화면에
     그대로(`st.error`) 출력**합니다 (디버깅 모드).

## 폴더 구조

```
.
├── app.py                       # 메인 실행 파일 (전체 화면 구성)
├── modules/
│   ├── fx_rates.py              # yfinance로 환율 데이터 조회
│   ├── cpi_data.py              # TÜİK TÜFE(CPI) 조회·YoY/MoM 계산 (TCMB 재공표/FRED/폴백)
│   ├── policy_rate.py           # 터키 기준금리 월별 데이터
│   ├── minimum_wage.py          # 터키 Gross 최저임금 자동 수집(CSGB 등) 및 환율 환산
│   ├── news_data.py             # 뉴스 더미(예시) 데이터 — 실시간 수집 실패 시 대체용
│   └── news_crawler.py          # 구글 뉴스 RSS 자동 수집 + Gemini REST API(requests 직접 호출) 한국어 번역
├── .streamlit/
│   ├── config.toml              # 테마/서버 설정
│   └── secrets.toml.example     # API 키 설정 예시 (실제 secrets.toml은 Git에 올리지 않음)
├── .env.example                 # API 키 설정 예시 (.env 파일용)
└── requirements.txt             # 필요한 파이썬 패키지 목록
```

## 실행 방법

1. 파이썬 패키지 설치

   ```bash
   pip install -r requirements.txt
   ```

2. (선택) AI 뉴스 번역 기능을 쓰려면 API 키를 설정합니다 — 아래 [AI 뉴스 번역 기능 설정](#-ai-뉴스-번역-기능-설정) 참고
   - 설정하지 않아도 앱은 정상적으로 실행되며, 뉴스 섹션은 예시(더미) 데이터로 표시됩니다.

3. 앱 실행

   ```bash
   streamlit run app.py
   ```

4. 브라우저에서 `http://localhost:8501` 접속 (스마트폰에서 보려면 같은 네트워크에서 `Network URL`로 접속)

## 🔑 AI 뉴스 번역 기능 설정 (Google Gemini)

실시간 뉴스 자동 수집 자체는 API 키 없이도 동작하지만(구글 뉴스는 무료 공개 RSS), 이를 **한국어로
번역**하려면 Google Gemini API 키(`GEMINI_API_KEY`)가 필요합니다.

번역은 `google-generativeai` SDK를 사용하지 않고, **Gemini REST API를 `requests`로 직접 호출**합니다
(Streamlit Cloud에서 SDK 버전에 따라 발생하던 `404 model not found` 오류를 근본적으로 피하기 위함).

- 엔드포인트: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}`
- 모델 순서(404일 때만 다음으로 우회): `gemini-1.5-flash` → `gemini-1.5-flash-latest` → `gemini-pro`

키 발급: [Google AI Studio](https://aistudio.google.com/apikey)

### 방법 1) Streamlit `secrets.toml` 사용 (권장, 배포 환경)

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

그 다음 `.streamlit/secrets.toml` 파일을 열어 실제 키를 입력합니다.

```toml
GEMINI_API_KEY = "your-gemini-api-key-here"
```

코드에서는 `st.secrets["GEMINI_API_KEY"]`로 안전하게 읽어옵니다.
Streamlit Community Cloud에 배포할 때는 앱 설정(App settings) → **Secrets** 메뉴에 동일한 내용을
붙여넣으면 됩니다.

### 방법 2) `.env` 파일 사용 (로컬 개발용 보조)

```bash
cp .env.example .env
```

그 다음 `.env` 파일을 열어 아래처럼 실제 발급받은 키를 입력합니다.

```
GEMINI_API_KEY=your-gemini-api-key-here
```

> ⚠️ `.env`와 `secrets.toml`은 모두 `.gitignore`에 등록되어 있어 실수로 GitHub에 올라가지 않습니다.

### 실시간 뉴스가 예시 데이터로만 나올 때

화면에 `실시간 뉴스를 가져오지 못했습니다` 경고가 보이면, 보통 아래 중 하나입니다.

1. Streamlit Cloud **Secrets**에 `GEMINI_API_KEY`가 없거나, 예시 값(`your-gemini-api-key-here`) 그대로임  
2. Secrets 저장 후 앱을 **Reboot**하지 않음  
3. 키가 잘못되었거나 Google AI Studio에서 비활성화됨  
4. Gemini REST API가 일시적으로 404/5xx 등을 반환함 (아래 디버그 메시지 참고)

Secrets 예시:

```toml
GEMINI_API_KEY = "AIzaSy...."
```

저장 후 앱 우측 하단 메뉴 → **Reboot app** 을 한 번 실행해 주세요.  
경고 메시지에 표시되는 **원인** 문구를 보면 어디를 고쳐야 하는지 바로 확인할 수 있습니다.

**디버깅 모드:** Gemini REST API 호출이 실패하면(HTTP 200이 아니면), 뉴스 섹션 위에
`🔧 [디버그] Gemini REST API 오류 — 모델: ... · HTTP ...` 형태로 **API가 반환한 응답 원문을
그대로** 보여줍니다. 여기 표시되는 HTTP 상태 코드와 본문(JSON 에러 메시지)을 보면
API 키 오류(400/403)인지, 모델 인식 실패(404)인지, 요청 한도 초과(429)인지 정확히
구분할 수 있습니다.

### `API 처리 지연` / 일일 사용량 초과 메시지가 뜰 때

Gemini 무료 티어는 **분당 요청 수(RPM)** 와 **일일 사용량** 한도가 있습니다.

- 분당 제한(429): 약 **3분** 동안 API 재호출을 막고 안내를 표시합니다.
- 일일 한도 초과: **다음 UTC 자정까지**(최소 18시간) API 재호출을 중단합니다. 1~3분 기다려도 복구되지 않습니다.
- 한도 초과 시에도 화면이 비지 않도록 **이전에 성공한 번역 캐시** → 없으면 **Google News 원문 RSS** 순으로 대체 표시합니다.
- 연속 새로고침/`지금 다시 시도`는 한도를 더 빨리 소진시킬 수 있으니 피하세요.
- 근본 해결: [Google AI Studio](https://aistudio.google.com/)에서 사용량 확인, 유료 플랜, 또는 별도 API 키 사용.

## 참고 사항

- 환율(EUR/TRY, USD/TRY, TRY/KRW)은 Yahoo Finance(`yfinance`) 데이터를 5분 캐시로 불러옵니다.
  `TRY/KRW` 티커가 야후에서 직접 지원되지 않는 경우, USD를 매개로 한 교차 환율(cross rate)로 자동 계산됩니다.
  최근 3개월 추이 그래프도 동일한 방식(직접 조회 → 실패 시 교차 환율 계산)으로 데이터를 가져옵니다.
- 터키 CPI(TÜFE)의 공식 출처는 **터키 통계청(TÜİK)** 입니다. 대시보드는 TCMB에 재공표된
  TÜİK 표를 우선 파싱하고, 실패 시 FRED(`TURCPIALLMINMEI`) 또는 공식 발표치 기반 오프라인
  폴백을 사용합니다. 데이터는 하루(`ttl=86400`)에 한 번 갱신됩니다.
- 터키 기준금리 데이터는 참고용 샘플 데이터입니다. 실제 서비스에서는 터키 중앙은행(TCMB)
  EVDS API 등 공식 데이터로 교체하는 것을 권장합니다.
- 터키 최저임금(Gross)은 CSGB 공식 페이지를 우선 크롤링하며, 하루(`ttl=86400`)에 한 번 갱신합니다.
  실패 시 TradingEconomics·현지 포털 순으로 시도하고, 모두 실패하면 2026년 공식 세전 금액(33,030 TRY)으로 대체합니다.
- 뉴스 자동 수집(`modules/news_crawler.py`)은 구글 뉴스 RSS 기사의 제목/요약만을 근거로 AI가
  번역·요약한 결과입니다. 중요한 의사결정 전에는 반드시 원문 기사 링크를 통해 사실관계를
  다시 확인해 주세요. 번역 결과는 비용 절감과 속도 향상(및 429 RPM 제한 회피)을 위해
  **최대 12시간 동안 캐시**되며, Gemini 호출은 기사별이 아니라 **배치 1회**로 처리됩니다.
  Gemini 호출은 `google-generativeai` SDK 없이 REST API를 `requests`로 직접 호출합니다.
- API 키가 없거나 수집/번역에 실패하면 `modules/news_data.py`의 더미 데이터로 자동 대체되므로,
  뉴스 섹션이 비어 보이는 일은 없습니다.
