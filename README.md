# 🇹🇷 터키 비즈니스 & 경제 동향 대시보드

터키 관련 사업/경제 정보를 한 화면에서 확인할 수 있는 **Streamlit** 기반 반응형 웹 대시보드입니다.
PC와 스마트폰 어디서든 보기 좋도록 반응형 레이아웃으로 만들어졌습니다.

## 주요 기능

1. **실시간 환율 카드** — EUR/TRY, USD/TRY, TRY/KRW 환율을 카드 형태로 크게 표시 (`yfinance` 사용)
   - 각 카드 아래에는 최근 3개월 환율 추이를 보여주는 미니 그래프가 함께 표시됩니다.
2. **터키 기준금리** — 최근 2년간 월별 기준금리를 라인 그래프로 표시 (`plotly` 사용)
3. **터키 최저임금**
   - 월 최저임금(**Gross, 세전 기준**)과 현재 환율 기준 EUR / USD / KRW 환산 금액
   - 시간당 최저임금(**Gross, 세전 기준**, 월 근무시간 255시간 가정)과 EUR / USD / KRW 환산 금액
4. **실시간 터키 뉴스 + AI 한국어 번역** — 무역·관세 / 이민·비자 / 노무·노동조합 / 물류·인프라 /
   외투기업·제조업 규제, 5가지 주제의 최신 뉴스를 구글 뉴스(Google News RSS)에서 자동 수집하고,
   **Google Gemini API(`gemini-1.5-flash`)** 로 한국어 번역·요약까지 자동으로 처리합니다.
   - 메인 화면에는 번역된 **한국어 제목만** 깔끔한 리스트로 표시됩니다.
   - 제목을 클릭(`st.expander`)하면 한국어 3줄 요약과 **원문 기사 링크**(새 창으로 열림)가 펼쳐집니다.
   - API 키가 없거나 수집/번역에 실패하면, 레이아웃 확인용 예시(더미) 뉴스로 자동 대체됩니다.

## 폴더 구조

```
.
├── app.py                       # 메인 실행 파일 (전체 화면 구성)
├── modules/
│   ├── fx_rates.py              # yfinance로 환율 데이터 조회
│   ├── policy_rate.py           # 터키 기준금리 월별 데이터
│   ├── minimum_wage.py          # 터키 최저임금 데이터 및 환율 환산
│   ├── news_data.py             # 뉴스 더미(예시) 데이터 — 실시간 수집 실패 시 대체용
│   └── news_crawler.py          # 구글 뉴스 RSS 자동 수집 + Gemini(gemini-1.5-flash) 한국어 번역
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
사용 모델: **`gemini-1.5-flash`** (가성비·속도에 유리)

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
4. 배포 환경에 `google-generativeai` 패키지가 아직 설치되지 않음 (`requirements.txt` 반영 + Reboot 필요)

Secrets 예시:

```toml
GEMINI_API_KEY = "AIzaSy...."
```

저장 후 앱 우측 하단 메뉴 → **Reboot app** 을 한 번 실행해 주세요.  
경고 메시지에 표시되는 **원인** 문구를 보면 어디를 고쳐야 하는지 바로 확인할 수 있습니다.

## 참고 사항

- 환율(EUR/TRY, USD/TRY, TRY/KRW)은 Yahoo Finance(`yfinance`) 데이터를 5분 캐시로 불러옵니다.
  `TRY/KRW` 티커가 야후에서 직접 지원되지 않는 경우, USD를 매개로 한 교차 환율(cross rate)로 자동 계산됩니다.
  최근 3개월 추이 그래프도 동일한 방식(직접 조회 → 실패 시 교차 환율 계산)으로 데이터를 가져옵니다.
- 터키 기준금리, 최저임금 데이터는 참고용 샘플 데이터입니다. 실제 서비스에서는 터키 중앙은행(TCMB)
  EVDS API, 터키 정부 발표 자료 등 공식 데이터로 교체하는 것을 권장합니다.
- 뉴스 자동 수집(`modules/news_crawler.py`)은 구글 뉴스 RSS 기사의 제목/요약만을 근거로 AI가
  번역·요약한 결과입니다. 중요한 의사결정 전에는 반드시 원문 기사 링크를 통해 사실관계를
  다시 확인해 주세요. 번역 결과는 비용 절감과 속도 향상(및 429 RPM 제한 회피)을 위해
  **6시간 동안 캐시**되며, Gemini 호출은 기사별이 아니라 **배치 1~2회**로 처리됩니다.
- API 키가 없거나 수집/번역에 실패하면 `modules/news_data.py`의 더미 데이터로 자동 대체되므로,
  뉴스 섹션이 비어 보이는 일은 없습니다.
