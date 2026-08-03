# =============================================================================
# news_crawler.py
# -----------------------------------------------------------------------------
# 이 파일은 "실시간 터키 뉴스 자동 수집 + AI 한국어 번역" 기능을 담당합니다.
#
# 전체 흐름 (아래로 갈수록 더 구체적인 작업입니다):
#   1) feedparser로 구글 뉴스(Google News) RSS에서 터키 관련 기사 5개 주제를 수집
#   2) 각 기사의 제목/요약(원문, 보통 영어 또는 터키어)을 정리
#   3) Google Gemini API(google-generativeai)를 이용해 한국어로 번역 + 3줄 요약
#   4) 결과를 Streamlit 캐시(@st.cache_data, 6시간)에 저장해서
#      같은 6시간 안에는 API를 다시 호출하지 않도록 함 (비용 절감 + 속도 향상)
#      ※ 번역은 기사별 호출이 아니라 배치 1~2회로 묶어 429(RPM 제한)를 피합니다.
#
# ⚠️ 이 모듈은 modules/news_data.py(더미 뉴스)를 대체하는 것이 아니라,
#    "새로운 실데이터 소스"로 추가된 것입니다. app.py에서는 이 모듈이
#    데이터를 가져오지 못하는 경우(예: API 키 미설정, 네트워크 오류)를 대비해
#    기존 news_data.py의 더미 데이터를 그대로 대체(fallback) 화면으로 사용합니다.
#    즉, 기존 코드 구조를 전혀 건드리지 않고 "새 모듈을 추가"하는 방식입니다.
#
# -----------------------------------------------------------------------------
# 🔑 API 키 설정 방법 (초보자를 위한 안내)
# -----------------------------------------------------------------------------
# 이 모듈은 Google Gemini API 키(GEMINI_API_KEY)를 아래 두 가지 방법 중
# 편한 방법으로 읽어옵니다.
# (설정하지 않으면, AI 번역 기능은 자동으로 비활성화되고 더미 뉴스가 대신 표시됩니다.)
#
# [방법 1] Streamlit secrets.toml 사용 (배포 환경 추천, 권장)
#   1. 프로젝트의 ".streamlit/secrets.toml" 파일에 아래처럼 적어줍니다.
#        GEMINI_API_KEY = "your-gemini-api-key-here"
#   2. 코드에서는 st.secrets["GEMINI_API_KEY"] 로 안전하게 읽어옵니다.
#   3. Streamlit Community Cloud에 배포할 때는 "App settings > Secrets" 메뉴에
#      동일한 내용을 붙여넣으면 됩니다.
#
# [방법 2] .env 파일 사용 (로컬 개발 환경용 보조)
#   1. 프로젝트 최상위 폴더에 ".env" 파일을 만듭니다.
#   2. 아래처럼 한 줄을 적어줍니다. (실제 발급받은 키로 교체)
#        GEMINI_API_KEY=your-gemini-api-key-here
#   3. ".env" 파일은 절대 GitHub 등에 올리면 안 되므로, .gitignore에 이미 등록해 두었습니다.
#
# Gemini API 키는 Google AI Studio(https://aistudio.google.com/apikey)에서 발급받을 수 있습니다.
# =============================================================================

import os
import re
import json
import time
import html as html_module
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote_plus

import requests
import feedparser
import streamlit as st

# python-dotenv는 로컬 개발 시 .env 파일을 읽어오기 위한 라이브러리입니다.
# 설치되어 있지 않거나 .env 파일이 없어도 에러 없이 넘어가도록 처리합니다.
try:
    from dotenv import load_dotenv

    load_dotenv()  # 프로젝트 루트의 .env 파일을 찾아서 환경변수로 등록합니다.
except ImportError:
    pass

# google-generativeai 패키지 (Gemini API 호출용).
# 설치되어 있지 않으면 None으로 두고, 실제로 번역을 시도할 때에만 에러 메시지를 보여줍니다.
# 설치 방법: pip install google-generativeai
try:
    import google.generativeai as genai
except ImportError:
    genai = None


# =============================================================================
# 1. 뉴스 수집 대상 "5가지 주제" 정의
# -----------------------------------------------------------------------------
# 터키 현지에서 공장/사업장을 운영하는 한국 기업 입장에서 중요한 5가지 주제를
# 미리 정의해 두고, 주제별로 구글 뉴스에서 검색할 영어 키워드를 지정합니다.
# (구글 뉴스는 한국어보다 영어 키워드로 검색했을 때 더 다양한 국제 뉴스를 찾아줍니다.)
# =============================================================================
NEWS_TOPICS = [
    {
        "key": "trade_customs",
        "label_kr": "무역·관세",
        "query": "Turkey trade OR Turkey customs OR Turkey tariff OR Turkey import export",
    },
    {
        "key": "immigration_visa",
        "label_kr": "이민·비자",
        "query": "Turkey immigration OR Turkey work permit OR Turkey foreigner visa",
    },
    {
        "key": "labor_union",
        "label_kr": "노무·노동조합",
        "query": "Turkey labor union OR Turkey strike OR Turkey employment law OR Turkey minimum wage",
    },
    {
        "key": "logistics_infra",
        "label_kr": "물류·인프라",
        "query": "Turkey logistics OR Turkey port OR Turkey transportation infrastructure",
    },
    {
        "key": "manufacturing_regulation",
        "label_kr": "외투기업·제조업 규제",
        "query": "Turkey foreign investment OR Turkey manufacturing regulation",
    },
]

# 한 번에 캐시가 갱신될 때 API 호출 비용을 통제하기 위한 기본값들입니다.
DEFAULT_MAX_ARTICLES_PER_TOPIC = 1  # 주제(5개)당 몇 개의 기사를 가져올지 (5개 주제 x 1개 = 총 5개 기사)
CACHE_TTL_SECONDS = 60 * 60 * 12  # 12시간 (성공한 번역 결과 — 갱신 호출 자체를 줄임)
BATCH_API_SLEEP_SECONDS = 4  # 배치를 2번 이상 나눠 호출할 때, 호출 사이 대기 시간(초)
# ⚠️ 429가 난 뒤 새로고침할 때마다 API를 다시 치면, 제한이 더 오래가거나 일일 한도를
# 더 빨리 소진합니다. 그래서 429 결과는 아래 쿨다운 시간 동안 재호출하지 않습니다.
RATE_LIMIT_COOLDOWN_SECONDS = 180  # 분당(RPM) 제한: 3분 동안 재호출 금지
# 일일 한도는 1시간 뒤 재시도해도 거의 복구되지 않으므로, 기본적으로 오래 막습니다.
# (실제 적용 시간은 _daily_quota_cooldown_seconds()가 UTC 자정+여유분으로 계산)
DAILY_QUOTA_COOLDOWN_SECONDS = 60 * 60 * 18  # 최소 18시간
# Gemini 무료 티어는 대략 분당 15회(15 RPM) + 일일 요청 한도가 있습니다.
API_RATE_LIMIT_MESSAGE = (
    "현재 API 처리 지연 중입니다. 약 3분 후 새로고침 해주세요. "
    "(연속 새로고침은 제한을 더 악화시킬 수 있습니다)"
)
API_DAILY_QUOTA_MESSAGE = (
    "Gemini 무료 티어 일일 사용량을 초과한 것 같습니다. "
    "API 재호출을 중단하고, 이전에 번역해 둔 뉴스 또는 원문 RSS로 대체 표시합니다. "
    "내일 다시 시도하거나 Google AI Studio에서 사용량/플랜을 확인해 주세요."
)

# 프로세스 전역 쿨다운 상태.
# 429가 난 뒤에도 예외는 @st.cache_data에 저장되지 않아, 새로고침할 때마다
# Gemini를 다시 호출하며 제한이 더 길어지거나 일일 한도를 소진합니다.
# 그래서 여기서 "재호출 금지 시각"을 기억해 두었다가, 쿨다운이 끝날 때까지
# API를 치지 않고 같은 안내 메시지만 반환합니다.
_cooldown_state: dict = {"until": 0.0, "error": "", "kind": ""}


# =============================================================================
# 2. 구글 뉴스(Google News) RSS에서 원문 기사 목록 가져오기
# =============================================================================
def _build_google_news_rss_url(query: str, hl: str = "tr", gl: str = "TR") -> str:
    """
    검색어(query)를 구글 뉴스 RSS 검색 URL로 바꿔줍니다.

    Parameters
    ----------
    query : str
        검색할 키워드 (예: "Turkey trade OR Turkey customs")
    hl : str
        언어(host language) 설정. "tr" = 터키어
    gl : str
        지역(geo location) 설정. "TR" = 터키
        -> hl/gl을 터키로 지정하면 "터키 지역 설정"으로 검색 결과가 필터링됩니다.
    """
    encoded_query = quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


class _HTMLTagStripper(HTMLParser):
    """
    RSS 요약(summary) 필드에는 종종 <a href="...">...</a> 같은 HTML 태그가
    섞여 있습니다. 이 클래스는 태그를 제거하고 순수 텍스트만 남겨줍니다.
    (별도의 외부 라이브러리(BeautifulSoup 등) 없이 파이썬 표준 라이브러리만으로 구현)
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []

    def handle_data(self, data):
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _strip_html(raw_html: str) -> str:
    """HTML 태그를 제거하고, 여러 개의 공백/줄바꿈을 하나의 공백으로 정리합니다."""
    if not raw_html:
        return ""
    try:
        stripper = _HTMLTagStripper()
        stripper.feed(raw_html)
        text = stripper.get_text()
    except Exception:
        # 혹시 파싱이 실패하더라도 정규식으로 태그만이라도 제거해서 최소한의 결과를 돌려줍니다.
        text = re.sub(r"<[^>]+>", "", raw_html)
    text = html_module.unescape(text)  # "&amp;" 같은 HTML 엔티티를 실제 문자로 변환
    return " ".join(text.split())


def _format_published_date(entry) -> str:
    """RSS 항목의 발행일을 'YYYY-MM-DD' 형태로 통일합니다."""
    parsed_time = entry.get("published_parsed")
    if parsed_time:
        try:
            return datetime(*parsed_time[:6]).strftime("%Y-%m-%d")
        except Exception:
            pass
    return entry.get("published", "날짜 미상")[:10]


def _fetch_rss_entries(url: str, timeout: int = 10):
    """
    RSS 피드 URL에 접속해서 항목(entry) 목록을 가져옵니다.

    feedparser.parse(url)을 바로 쓰지 않고 requests로 먼저 내려받는 이유:
    - requests는 timeout(응답 대기 시간 제한)을 지정할 수 있어서, 네트워크가
      느리거나 응답이 없을 때 프로그램이 무한정 멈춰 있는 것을 방지할 수 있습니다.
    - User-Agent 헤더를 지정해서 일부 서버가 "브라우저가 아닌 요청"을
      차단하는 것을 방지합니다.
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TurkeyDashboardBot/1.0)"},
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return feed.entries
    except Exception:
        # 네트워크 오류, 타임아웃, HTTP 오류(4xx/5xx) 등 어떤 문제든 여기서 잡아서
        # 빈 리스트를 돌려주면 화면(app.py)에서는 "해당 주제 뉴스 없음"으로 처리됩니다.
        return []


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def collect_raw_news_for_topic(topic_key: str, query: str, max_results: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """
    주제 1개에 대해 구글 뉴스 RSS를 조회하고, 번역하기 전 '원문 그대로'의
    기사 정보를 정리해서 리스트로 반환합니다.

    반환되는 각 항목의 형태:
        {
            "title_original": "원문 제목",
            "summary_original": "원문 요약(가능하면)",
            "link": "기사 원문(또는 구글 뉴스 경유) 링크",
            "source": "언론사 이름",
            "date": "YYYY-MM-DD",
        }
    """
    url = _build_google_news_rss_url(query)
    entries = _fetch_rss_entries(url)

    results = []
    for entry in entries[:max_results]:
        source_name = entry.get("source", {}).get("title", "") or "Google News"

        raw_title = (entry.get("title") or "").strip()
        # 구글 뉴스는 제목 끝에 " - 언론사명"을 자동으로 붙여주는 경우가 많아서,
        # 번역할 때 불필요한 중복이 생기지 않도록 이 부분을 제거합니다.
        suffix = f" - {source_name}"
        if source_name and raw_title.endswith(suffix):
            raw_title = raw_title[: -len(suffix)]

        results.append(
            {
                "title_original": raw_title,
                "summary_original": _strip_html(entry.get("summary", "")),
                "link": entry.get("link", ""),
                "source": source_name,
                "date": _format_published_date(entry),
            }
        )

    return results


def collect_all_raw_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """
    NEWS_TOPICS에 정의된 5가지 주제를 모두 순회하면서 원문 기사를 수집하고,
    각 기사에 "category"(한글 주제명)를 붙여서 하나의 리스트로 합쳐줍니다.
    """
    all_news = []
    for topic in NEWS_TOPICS:
        topic_news = collect_raw_news_for_topic(topic["key"], topic["query"], max_per_topic)
        for item in topic_news:
            item_with_category = dict(item)
            item_with_category["category"] = topic["label_kr"]
            all_news.append(item_with_category)
    return all_news


# =============================================================================
# 3. AI 번역/요약 (Google Gemini API — google-generativeai)
# -----------------------------------------------------------------------------
# 가성비와 속도가 좋은 gemini-1.5-flash 모델을 사용합니다.
# System Instruction에는 "한국인 비즈니스/제조업 경영진이 읽기 편한 전문적인
# 어투로 터키어/영어 뉴스를 한국어로 번역 및 요약"하도록 지시합니다.
# =============================================================================
# 우선 사용할 모델. 후보를 많이 두면 실패 시마다 API를 여러 번 호출해
# 429(RPM) 제한을 더 쉽게 유발하므로, 후보는 최소로 유지합니다.
GEMINI_MODEL_NAME = "gemini-1.5-flash"
# 일일 한도 보호: 모델 폴백을 없애 실패 시 추가 호출이 나가지 않게 합니다.
GEMINI_MODEL_CANDIDATES = (
    "gemini-1.5-flash",
)

# 예시 파일에 들어 있는 자리표시자 값. 이런 값이 secrets에 있으면
# "키가 설정된 것처럼" 보이지만 실제 API 호출은 실패합니다.
_PLACEHOLDER_API_KEYS = {
    "",
    "your-gemini-api-key-here",
    "YOUR_GEMINI_API_KEY",
    "xxxxxxxx",
    "xxx",
}

# GenerativeModel의 system_instruction 으로 전달되는 지시문입니다.
# 배치 번역이므로, 여러 기사를 한 번에 받아 JSON 배열로 돌려주도록 지시합니다.
TRANSLATION_SYSTEM_PROMPT = (
    "한국인 비즈니스/제조업 경영진이 읽기 편한 전문적인 어투로 "
    "터키어/영어 뉴스를 한국어로 번역 및 요약해라. "
    "구어체나 과장된 표현은 사용하지 말고, 원문에 없는 내용을 추측해서 추가하지 마세요. "
    "입력으로 여러 기사가 주어지면 각 기사를 모두 번역/요약하고, "
    "응답은 반드시 아래 JSON 형식 그대로만 출력하세요. (그 외 설명 문장 금지)\n"
    '{"articles":[{"id":0,"title_kr":"번역된 한국어 제목","summary_kr":["요약1","요약2","요약3"]}]}'
)


class NewsFetchError(RuntimeError):
    """뉴스 수집/번역 실패 시, Streamlit 캐시에 실패 결과가 오래
    남지 않도록 예외로 올리는 데 사용하는 내부 예외 클래스입니다."""

    pass


class GeminiRateLimitError(NewsFetchError):
    """Gemini 429 / Quota Exceeded 전용 예외."""

    def __init__(self, message: str, kind: str = "minute"):
        super().__init__(message)
        # kind: "minute" (분당 RPM) 또는 "daily" (일일 한도)
        self.kind = kind


def _is_rate_limit_error(exc: Exception) -> bool:
    """예외 메시지가 429 / quota / rate limit 인지 판별합니다."""
    text = str(exc).lower()
    return (
        "429" in text
        or "quota" in text
        or "rate limit" in text
        or "rate_limit" in text
        or "resource exhausted" in text
        or "too many requests" in text
    )


def _is_daily_quota_error(exc: Exception) -> bool:
    """일일 사용량 초과인지 판별합니다. (1분만 기다려서는 해결되지 않음)"""
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "per day",
            "perday",
            "per_day",
            "daily",
            "day_tier",
            "requestsperday",
            "generate_content_free_tier_requests",
        )
    )


def _is_model_not_found_error(exc: Exception) -> bool:
    """모델이 없어서 다음 후보를 시도해도 되는 오류인지 판별합니다."""
    text = str(exc).lower()
    return ("not found" in text and "model" in text) or "404" in text


def _build_batch_user_prompt(raw_news_batch: list) -> str:
    """
    여러 기사(제목/요약)를 하나의 JSON 배열로 묶어 Gemini에 보낼 프롬프트를 만듭니다.
    이렇게 하면 기사 수와 관계없이 API를 1번만 호출할 수 있습니다.
    """
    payload = []
    for idx, item in enumerate(raw_news_batch):
        payload.append(
            {
                "id": idx,
                "title": item.get("title_original", ""),
                "summary": item.get("summary_original", "")
                or "(제공된 요약이 없어 제목만으로 판단해야 합니다)",
            }
        )

    return (
        "아래 JSON 배열의 각 뉴스 기사를 한국어로 번역하고, 핵심 내용을 정확히 3줄로 요약해 주세요.\n"
        "입력 id 값을 그대로 응답 articles[].id 에 넣어 주세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _normalize_summary_lines(summary_kr, fallback_line: str = "요약 내용을 생성하지 못했습니다.") -> list:
    """summary_kr 값을 항상 '최대 3개 문자열 리스트'로 정규화합니다."""
    if not isinstance(summary_kr, list) or len(summary_kr) == 0:
        summary_kr = [str(summary_kr or fallback_line)]
    summary_kr = [str(line).strip() for line in summary_kr[:3] if str(line).strip()]
    if not summary_kr:
        summary_kr = [fallback_line]
    return summary_kr


def _parse_batch_translation_response(raw_text: str, raw_news_batch: list) -> list:
    """
    배치 번역 응답(JSON)을 파싱해, 입력 기사 순서에 맞는
    [{title_kr, summary_kr}, ...] 리스트로 변환합니다.
    """
    cleaned = re.sub(r"^```(json)?|```$", "", (raw_text or "").strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)

    # 응답이 {"articles":[...]} 또는 그냥 [...] 둘 다 허용
    if isinstance(data, dict):
        articles = data.get("articles")
    else:
        articles = data

    if not isinstance(articles, list) or not articles:
        raise ValueError("배치 번역 응답에 articles 배열이 없습니다.")

    # id -> 번역 결과 매핑
    by_id = {}
    for article in articles:
        if not isinstance(article, dict):
            continue
        try:
            article_id = int(article.get("id"))
        except (TypeError, ValueError):
            continue
        title_kr = str(article.get("title_kr") or "").strip()
        summary_kr = _normalize_summary_lines(article.get("summary_kr"))
        if title_kr:
            by_id[article_id] = {"title_kr": title_kr, "summary_kr": summary_kr}

    results = []
    for idx, raw in enumerate(raw_news_batch):
        translated = by_id.get(idx)
        if translated:
            results.append(translated)
        else:
            # 일부 기사만 빠진 경우에도 화면이 비지 않도록 최소한의 fallback을 넣습니다.
            results.append(
                {
                    "title_kr": raw.get("title_original") or f"기사 {idx + 1}",
                    "summary_kr": ["이 기사의 번역 결과를 받지 못했습니다."],
                }
            )
    return results


def _normalize_api_key(raw_value) -> str | None:
    """키 문자열을 정리하고, 자리표시자/빈 값이면 None을 반환합니다."""
    if raw_value is None:
        return None
    value = str(raw_value).strip().strip('"').strip("'")
    if not value or value.lower() in {k.lower() for k in _PLACEHOLDER_API_KEYS}:
        return None
    return value


def _get_gemini_api_key():
    """
    Gemini API 키를 안전하게 읽어옵니다.

    우선순위:
      1) Streamlit secrets → st.secrets["GEMINI_API_KEY"]  (배포 환경 권장)
      2) 환경변수 / .env 파일의 GEMINI_API_KEY             (로컬 개발용 보조)

    secrets.toml 파일이 없거나 키가 없거나, 예시용 자리표시자 값이면 None을 반환합니다.
    """
    try:
        # st.secrets["GEMINI_API_KEY"] 형태로 안전하게 접근합니다.
        # secrets.toml 자체가 없는 환경에서는 예외가 날 수 있으므로 try-except로 감쌉니다.
        if "GEMINI_API_KEY" in st.secrets:
            normalized = _normalize_api_key(st.secrets["GEMINI_API_KEY"])
            if normalized:
                return normalized
    except Exception:
        pass

    return _normalize_api_key(os.getenv("GEMINI_API_KEY"))


def is_ai_translation_configured() -> bool:
    """
    화면(app.py)에서 'AI 번역 기능을 쓸 수 있는지'를 미리 확인할 때 사용하는 함수입니다.
    GEMINI_API_KEY가 설정되어 있지 않으면 False를 반환하고,
    app.py는 이때 더미 뉴스로 대체합니다.
    """
    return bool(_get_gemini_api_key())


def _extract_response_text(response) -> str:
    """Gemini 응답 객체에서 텍스트를 안전하게 꺼냅니다."""
    try:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
    except Exception:
        # response.text 접근 시 finish_reason 등으로 예외가 날 수 있어 candidates를 직접 확인합니다.
        pass

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            chunks = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
            if chunks:
                return "\n".join(chunks).strip()
    except Exception:
        pass
    return ""


def _raise_rate_limit(exc: Exception):
    """429/쿼터 예외를 분당/일일 종류에 맞는 GeminiRateLimitError로 변환해 올립니다."""
    if _is_daily_quota_error(exc):
        raise GeminiRateLimitError(API_DAILY_QUOTA_MESSAGE, kind="daily") from exc
    raise GeminiRateLimitError(API_RATE_LIMIT_MESSAGE, kind="minute") from exc


def _call_gemini_once(api_key: str, user_prompt: str) -> str:
    """
    Gemini API를 1회 호출해 텍스트 응답을 반환합니다.
    모델 후보는 '모델을 찾을 수 없음'일 때만 다음으로 넘어가고,
    429가 나면 즉시 중단합니다. (폴백을 남발하면 RPM이 더 소모됩니다.)
    """
    if genai is None:
        raise RuntimeError(
            "google-generativeai 패키지가 설치되어 있지 않습니다. "
            "requirements.txt에 google-generativeai가 있는지 확인하고 앱을 Reboot 해 주세요."
        )

    genai.configure(api_key=api_key)
    last_error = None

    for model_index, model_name in enumerate(GEMINI_MODEL_CANDIDATES):
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=TRANSLATION_SYSTEM_PROMPT,
                generation_config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json",
                },
            )
            response = model.generate_content(user_prompt)
            raw_text = _extract_response_text(response)
            if not raw_text:
                raise RuntimeError(f"모델({model_name})이 빈 응답을 반환했습니다.")
            return raw_text
        except GeminiRateLimitError:
            raise
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _raise_rate_limit(exc)
            last_error = exc
            # 모델 ID가 없는 경우에만 다음 후보를 시도합니다.
            # 그 외 오류에서 계속 시도하면 요청 수만 늘어 429를 유발합니다.
            if _is_model_not_found_error(exc) and model_index < len(GEMINI_MODEL_CANDIDATES) - 1:
                time.sleep(BATCH_API_SLEEP_SECONDS)
                continue
            break

    raise RuntimeError(f"Gemini 번역 호출 실패: {last_error}")


def _translate_news_batch_with_gemini(api_key: str, raw_news_list: list) -> list:
    """
    여러 기사를 한 번에(배치로) 번역합니다.

    - 기본: 전체 기사를 묶어 API를 딱 1번만 호출
    - 기사가 많아 응답이 잘릴 가능성에 대비해, 필요하면 최대 2개 배치로 나눕니다.
      (2번째 배치 호출 전에는 time.sleep(4)로 RPM 제한을 피합니다.)
    """
    if not raw_news_list:
        return []

    # 보통 5개 전후라 1번 호출로 충분합니다. 8개 초과일 때만 2배치로 나눕니다.
    if len(raw_news_list) <= 8:
        batches = [raw_news_list]
    else:
        mid = (len(raw_news_list) + 1) // 2
        batches = [raw_news_list[:mid], raw_news_list[mid:]]

    all_translated = []
    for batch_index, batch in enumerate(batches):
        if batch_index > 0:
            # 배치를 2번 호출해야 할 때만, 무료 티어 15 RPM을 넘지 않도록 대기합니다.
            time.sleep(BATCH_API_SLEEP_SECONDS)

        raw_text = _call_gemini_once(api_key, _build_batch_user_prompt(batch))
        batch_translated = _parse_batch_translation_response(raw_text, batch)
        all_translated.extend(batch_translated)

    return all_translated


def _humanize_gemini_error(exc: Exception) -> str:
    """Gemini/네트워크 예외 메시지를 사용자가 조치하기 쉬운 안내로 바꿉니다."""
    if isinstance(exc, GeminiRateLimitError):
        return API_DAILY_QUOTA_MESSAGE if exc.kind == "daily" else API_RATE_LIMIT_MESSAGE
    if _is_daily_quota_error(exc):
        return API_DAILY_QUOTA_MESSAGE
    if _is_rate_limit_error(exc):
        return API_RATE_LIMIT_MESSAGE

    text = str(exc)
    lowered = text.lower()

    if API_DAILY_QUOTA_MESSAGE in text:
        return API_DAILY_QUOTA_MESSAGE
    if API_RATE_LIMIT_MESSAGE in text:
        return API_RATE_LIMIT_MESSAGE

    if "api key" in lowered or "api_key" in lowered or ("invalid" in lowered and "key" in lowered):
        return (
            "Gemini API 키가 올바르지 않습니다. "
            "Streamlit Cloud → App settings → Secrets 에 "
            '`GEMINI_API_KEY = "실제키"` 형태로 넣었는지 확인한 뒤 Reboot 해 주세요.'
        )
    if "permission" in lowered or "403" in lowered:
        return (
            "Gemini API 권한 오류(403)입니다. "
            "Google AI Studio에서 키를 다시 발급받고, Generative Language API 사용이 가능한지 확인해 주세요."
        )
    if "not found" in lowered and "model" in lowered:
        return (
            f"요청한 Gemini 모델을 찾을 수 없습니다. ({text}) "
            "모델 이름(gemini-1.5-flash)이 계정에서 지원되는지 확인해 주세요."
        )
    if "google-generativeai" in lowered or "패키지" in text:
        return text
    return f"Gemini/네트워크 오류: {text}"


def _daily_quota_cooldown_seconds() -> int:
    """
    일일 한도 쿨다운 시간(초).
    다음 UTC 자정(+10분 여유)까지로 잡아, 한도 리셋 전에는 Gemini를 다시 치지 않습니다.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    next_reset = (now + timedelta(days=1)).replace(hour=0, minute=10, second=0, microsecond=0)
    until_reset = int((next_reset - now).total_seconds())
    return max(DAILY_QUOTA_COOLDOWN_SECONDS, until_reset)


def _activate_rate_limit_cooldown(exc: GeminiRateLimitError) -> None:
    """429/일일 한도 오류 발생 시각부터 쿨다운을 겁니다."""
    seconds = (
        _daily_quota_cooldown_seconds() if exc.kind == "daily" else RATE_LIMIT_COOLDOWN_SECONDS
    )
    _cooldown_state["until"] = time.time() + seconds
    _cooldown_state["error"] = str(exc) or _humanize_gemini_error(exc)
    _cooldown_state["kind"] = exc.kind


def clear_news_fetch_cooldown() -> None:
    """쿨다운을 해제해 즉시 Gemini 재시도를 허용합니다. (UI '다시 시도' 버튼용)"""
    _cooldown_state["until"] = 0.0
    _cooldown_state["error"] = ""
    _cooldown_state["kind"] = ""


def get_news_fetch_cooldown_remaining() -> int:
    """쿨다운 잔여 초(없으면 0)를 반환합니다."""
    remaining = int(_cooldown_state["until"] - time.time())
    return max(0, remaining)


@st.cache_resource
def _last_good_news_store() -> dict:
    """
    프로세스 수명 동안 마지막 성공 번역을 보관합니다.
    일일 한도/429가 나도 이전에 받아 둔 한국어 뉴스를 계속 보여주기 위함입니다.
    """
    return {"news": [], "saved_at": 0.0}


def _save_last_good_news(news: list) -> None:
    """성공한 번역 결과를 장기 보관 저장소에 넣습니다."""
    if not news:
        return
    store = _last_good_news_store()
    store["news"] = list(news)
    store["saved_at"] = time.time()


def _load_last_good_news() -> list:
    """보관 중인 마지막 성공 번역을 반환합니다. 없으면 빈 리스트."""
    store = _last_good_news_store()
    news = store.get("news") or []
    return list(news) if news else []


def _raw_news_as_display_items(raw_news_list: list) -> list:
    """
    Gemini 없이 RSS 원문만으로 화면 표시용 항목을 만듭니다.
    일일 한도 초과 시에도 '가짜 더미' 대신 실제 최신 기사 링크를 보여줍니다.
    """
    display_items = []
    for raw in raw_news_list:
        title = (raw.get("title_original") or "").strip() or "(제목 없음)"
        summary = (raw.get("summary_original") or "").strip()
        summary_lines = []
        if summary:
            # 원문 요약을 최대 3줄로 나눕니다.
            chunks = [part.strip() for part in re.split(r"[\n\.!?]+", summary) if part.strip()]
            summary_lines = chunks[:3] if chunks else [summary[:280]]
        if not summary_lines:
            summary_lines = [
                "AI 번역 한도 초과로 원문 제목/요약만 표시합니다. 원문 링크에서 내용을 확인해 주세요."
            ]
        display_items.append(
            {
                "category": raw.get("category", ""),
                "title_kr": f"{title} (원문)",
                "summary_kr": summary_lines,
                "link": raw.get("link", ""),
                "source": raw.get("source", "Google News"),
                "date": raw.get("date", ""),
            }
        )
    return display_items


def _rss_only_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC) -> list:
    """Google News RSS만 수집해 표시용으로 반환합니다 (Gemini 호출 없음)."""
    try:
        raw_news_list = collect_all_raw_news(max_per_topic=max_per_topic)
        return _raw_news_as_display_items(raw_news_list)
    except Exception:
        return []


def _fallback_news_payload(error_message: str, error_kind: str, max_per_topic: int) -> dict:
    """
    Gemini 실패/쿨다운 시 사용할 대체 뉴스 payload.
    우선순위: 마지막 성공 번역 → RSS 원문 → 빈 목록(앱에서 더미로 대체).
    """
    last_good = _load_last_good_news()
    if last_good:
        return {
            "news": last_good,
            "error": error_message,
            "cooldown_remaining": get_news_fetch_cooldown_remaining(),
            "error_kind": error_kind,
            "news_mode": "stale_cache",
        }

    rss_news = _rss_only_news(max_per_topic=max_per_topic)
    if rss_news:
        return {
            "news": rss_news,
            "error": error_message,
            "cooldown_remaining": get_news_fetch_cooldown_remaining(),
            "error_kind": error_kind,
            "news_mode": "rss_only",
        }

    return {
        "news": [],
        "error": error_message,
        "cooldown_remaining": get_news_fetch_cooldown_remaining(),
        "error_kind": error_kind,
        "news_mode": "empty",
    }


# =============================================================================
# 4. 최종 공개 함수 — app.py에서는 fetch_ai_translated_news()를 호출하면 됩니다.
# -----------------------------------------------------------------------------
# 성공한 번역 결과만 @st.cache_data(ttl=21600, 6시간)으로 캐시합니다.
# 429/일일 한도 실패는 예외로 올리되, fetch 단계에서 쿨다운을 걸어
# 새로고침해도 Gemini를 다시 호출하지 않습니다.
# 번역은 기사별 개별 호출이 아니라 배치 1~2회로 RPM 제한을 피합니다.
# =============================================================================
@st.cache_data(
    ttl=CACHE_TTL_SECONDS,  # 6시간 = 21600초
    show_spinner="최신 터키 뉴스를 수집하고 Gemini로 한 번에 번역하는 중입니다...",
)
def _cached_ai_translated_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """성공한 뉴스 리스트만 캐시합니다. 실패 시 NewsFetchError를 발생시킵니다."""
    try:
        if genai is None:
            raise NewsFetchError(
                "google-generativeai 패키지가 설치되어 있지 않습니다. "
                "requirements.txt 반영 후 Streamlit Cloud에서 앱을 Reboot 해 주세요."
            )

        api_key = _get_gemini_api_key()
        if not api_key:
            raise NewsFetchError(
                "GEMINI_API_KEY가 설정되지 않았거나 예시 값(your-gemini-api-key-here) 그대로입니다."
            )

        raw_news_list = collect_all_raw_news(max_per_topic=max_per_topic)
        if not raw_news_list:
            raise NewsFetchError(
                "구글 뉴스 RSS에서 기사를 가져오지 못했습니다. "
                "네트워크/방화벽 문제이거나 Google News RSS 접근이 차단되었을 수 있습니다."
            )

        # ★ 핵심: 기사마다 for-loop로 API를 치지 않고, 전체를 배치로 1~2번만 번역합니다.
        translated_parts = _translate_news_batch_with_gemini(api_key, raw_news_list)

        translated_news = []
        for raw, translated in zip(raw_news_list, translated_parts):
            translated_news.append(
                {
                    "category": raw["category"],
                    "title_kr": translated["title_kr"],
                    "summary_kr": translated["summary_kr"],
                    "link": raw["link"],
                    "source": raw["source"],
                    "date": raw["date"],
                }
            )

        if not translated_news:
            raise NewsFetchError("번역된 뉴스 결과가 비어 있습니다.")

        return translated_news
    except GeminiRateLimitError:
        # 429는 그대로 올려서 fetch 단계에서 쿨다운을 걸도록 합니다.
        raise
    except NewsFetchError:
        raise
    except Exception as exc:
        # 예기치 못한 예외도 앱이 멈추지 않도록 NewsFetchError로 감쌉니다.
        if _is_rate_limit_error(exc):
            _raise_rate_limit(exc)
        raise NewsFetchError(_humanize_gemini_error(exc)) from exc


def fetch_ai_translated_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC) -> dict:
    """
    app.py에서 사용하는 공개 함수입니다.
    예외가 나더라도 화면이 멈추지 않도록 항상 dict를 반환합니다.

    Returns
    -------
    dict
        {
            "news": [뉴스 dict ...],
            "error": None 또는 사용자용 오류 안내 문자열,
            "cooldown_remaining": 쿨다운 잔여 초(없으면 0),
            "error_kind": None | "minute" | "daily" | "other",
            "news_mode": "live" | "stale_cache" | "rss_only" | "empty",
        }
    """
    # 쿨다운 중이면 Gemini를 절대 다시 호출하지 않고, 보관 뉴스/RSS로 대체합니다.
    remaining = get_news_fetch_cooldown_remaining()
    if remaining > 0 and _cooldown_state["error"]:
        return _fallback_news_payload(
            error_message=_cooldown_state["error"],
            error_kind=_cooldown_state["kind"] or "minute",
            max_per_topic=max_per_topic,
        )

    try:
        news = _cached_ai_translated_news(max_per_topic=max_per_topic)
        # 성공하면 장기 보관 + 쿨다운 해제
        _save_last_good_news(news)
        clear_news_fetch_cooldown()
        return {
            "news": news,
            "error": None,
            "cooldown_remaining": 0,
            "error_kind": None,
            "news_mode": "live",
        }
    except GeminiRateLimitError as exc:
        _activate_rate_limit_cooldown(exc)
        return _fallback_news_payload(
            error_message=str(exc) or _humanize_gemini_error(exc),
            error_kind=exc.kind,
            max_per_topic=max_per_topic,
        )
    except NewsFetchError as exc:
        # 일반 실패도 가능하면 직전 성공 번역을 보여줍니다.
        last_good = _load_last_good_news()
        if last_good:
            return {
                "news": last_good,
                "error": str(exc),
                "cooldown_remaining": 0,
                "error_kind": "other",
                "news_mode": "stale_cache",
            }
        return {
            "news": [],
            "error": str(exc),
            "cooldown_remaining": 0,
            "error_kind": "other",
            "news_mode": "empty",
        }
    except Exception as exc:
        if _is_rate_limit_error(exc):
            rate_exc = GeminiRateLimitError(
                _humanize_gemini_error(exc),
                kind="daily" if _is_daily_quota_error(exc) else "minute",
            )
            _activate_rate_limit_cooldown(rate_exc)
            return _fallback_news_payload(
                error_message=str(rate_exc),
                error_kind=rate_exc.kind,
                max_per_topic=max_per_topic,
            )
        last_good = _load_last_good_news()
        if last_good:
            return {
                "news": last_good,
                "error": _humanize_gemini_error(exc),
                "cooldown_remaining": 0,
                "error_kind": "other",
                "news_mode": "stale_cache",
            }
        return {
            "news": [],
            "error": _humanize_gemini_error(exc),
            "cooldown_remaining": 0,
            "error_kind": "other",
            "news_mode": "empty",
        }


def get_ai_translated_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """
    하위 호환용 함수. 뉴스 리스트만 필요할 때 사용합니다.
    실패 시 빈 리스트를 반환합니다.
    """
    return fetch_ai_translated_news(max_per_topic=max_per_topic)["news"]