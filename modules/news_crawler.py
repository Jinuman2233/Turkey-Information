# =============================================================================
# news_crawler.py
# -----------------------------------------------------------------------------
# 이 파일은 "실시간 터키 뉴스 자동 수집 + AI 한국어 번역" 기능을 담당합니다.
#
# 전체 흐름 (아래로 갈수록 더 구체적인 작업입니다):
#   1) feedparser로 구글 뉴스(Google News) RSS에서 터키 '자동차 산업' 관련 기사를 수집
#      - 튀르키예어 키워드(otomotiv, otomobil ihracatı, araç üretimi, TOGG 등)로 검색
#      - 검색 쿼리 끝에 when:30d 를 붙여 최근 30일 이내 기사만 요청
#      - ★ Python에서 발행일을 다시 파싱해 30일보다 오래된 기사는 과감하게 drop
#      - 최신 발행순으로 상위 N개만 Gemini 번역에 전달
#   2) 각 기사의 제목/요약(원문, 보통 영어 또는 터키어)을 정리
#   3) Google Gemini REST API(https://generativelanguage.googleapis.com/v1beta/...)를
#      requests로 "직접" 호출해 한국어로 번역 + 3줄 요약합니다.
#      ⚠️ Streamlit Cloud에서 google-generativeai SDK 버전 호환성 문제로 반복적으로
#      404(모델 인식 실패)/통신 오류가 발생해, SDK 의존성을 완전히 제거하고
#      순수 REST 방식으로 직접 통신하도록 전면 개편했습니다.
#   4) 결과를 Streamlit 캐시(@st.cache_data, 12시간)에 저장해서
#      같은 시간 안에는 API를 다시 호출하지 않도록 함 (비용 절감 + 속도 향상)
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
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import quote_plus
from time import struct_time

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

# ⚠️ google-generativeai SDK는 더 이상 사용하지 않습니다.
# Streamlit Cloud 환경에서 SDK 버전에 따라 모델 인식 오류(404)가 반복적으로
# 발생해, Gemini REST API를 requests로 직접 호출하는 방식으로 전환했습니다.
# (아래 "3. AI 번역/요약" 섹션 참고)


# =============================================================================
# 1. 뉴스 수집 대상 — 터키 자동차 산업 (otomotiv) 중심
# -----------------------------------------------------------------------------
# 사용자가 원하는 "자동차 산업" 뉴스를 집중 수집하기 위해,
# 튀르키예어 키워드(otomotiv / otomobil / araç / TOGG 등)로 주제별 쿼리를 구성합니다.
# Google News RSS에는 각 쿼리 끝에 when:30d 가 자동으로 붙습니다.
# =============================================================================
NEWS_TOPICS = [
    {
        "key": "otomotiv_sanayi",
        "label_kr": "자동차 산업",
        "query": "Türkiye otomotiv sanayi OR otomotiv sanayi",
    },
    {
        "key": "otomobil_ihracati",
        "label_kr": "자동차 수출",
        "query": "otomobil ihracatı OR otomotiv ihracat",
    },
    {
        "key": "arac_uretimi",
        "label_kr": "차량 생산",
        "query": "araç üretimi OR otomotiv üretimi OR otomobil üretimi",
    },
    {
        "key": "togg_ev",
        "label_kr": "TOGG·전기차",
        "query": "TOGG OR elektrikli otomobil OR elektrikli araç Türkiye",
    },
    {
        "key": "otomotiv_yan_sanayi",
        "label_kr": "자동차 부품·투자",
        "query": "otomotiv yan sanayi OR otomotiv fabrika OR otomotiv yatırım",
    },
]

# NewsAPI 등 외부 API에서 쓸 자동차 산업 기본 검색식
NEWS_API_AUTOMOTIVE_QUERY = "(otomotiv OR araç OR otomobil OR TOGG)"

# 한 번에 캐시가 갱신될 때 API 호출 비용을 통제하기 위한 기본값들입니다.
# 최근 N일 이내 기사만 모은 뒤, 전역 최신순으로 상위 MAX_NEWS_FOR_TRANSLATION개만 Gemini에 전달합니다.
NEWS_LOOKBACK_DAYS = 30  # 오늘 기준 최근 30일(하드코딩 날짜 금지 — datetime으로 동적 계산)
DEFAULT_MAX_ARTICLES_PER_TOPIC = 5  # 주제당 후보 수집 상한(필터·정렬 전)
MAX_NEWS_FOR_TRANSLATION = 8  # Gemini 번역으로 넘길 최신 뉴스 개수(5~10 권장 범위)
# 주제/필터 로직이 바뀌면 캐시 키를 강제로 바꿔 예전(비자동차·오래된) 캐시를 쓰지 않습니다.
NEWS_CACHE_VERSION = "automotive-30d-v2"
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
# 모델 404/일시 통신 오류 등 — 영어 스택트레이스 대신 보여줄 안내
API_TRANSLATION_BUSY_MESSAGE = "번역 서버와 통신 중입니다. 잠시 후 다시 시도해 주세요."

# 프로세스 전역 쿨다운 상태.
# 429가 난 뒤에도 예외는 @st.cache_data에 저장되지 않아, 새로고침할 때마다
# Gemini를 다시 호출하며 제한이 더 길어지거나 일일 한도를 소진합니다.
# 그래서 여기서 "재호출 금지 시각"을 기억해 두었다가, 쿨다운이 끝날 때까지
# API를 치지 않고 같은 안내 메시지만 반환합니다.
_cooldown_state: dict = {"until": 0.0, "error": "", "kind": ""}


# =============================================================================
# 2. 구글 뉴스(Google News) RSS에서 원문 기사 목록 가져오기
# =============================================================================
def _lookback_cutoff(now: datetime | None = None) -> datetime:
    """
    '오늘' 기준으로 최근 NEWS_LOOKBACK_DAYS일 이전 시각(컷오프)을 반환합니다.
    하드코딩된 날짜는 사용하지 않습니다.
    """
    reference = now if now is not None else datetime.now()
    return reference - timedelta(days=NEWS_LOOKBACK_DAYS)


def _google_news_time_filter_suffix(lookback_days: int = NEWS_LOOKBACK_DAYS) -> str:
    """
    Google News 검색 쿼리에 붙일 기간 옵션입니다.
    예: when:30d  → 최근 30일 이내 기사만 검색
    """
    return f"when:{int(lookback_days)}d"


def _build_google_news_rss_url(
    query: str,
    hl: str = "tr",
    gl: str = "TR",
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> str:
    """
    검색어(query)를 구글 뉴스 RSS 검색 URL로 바꿔줍니다.
    검색어 끝에 when:{N}d 를 공백으로 정확히 붙여 최근 N일만 요청합니다.
    예: q=Türkiye+otomotiv+sanayi+when:30d

    Parameters
    ----------
    query : str
        검색할 키워드 (예: "Türkiye otomotiv sanayi OR otomotiv sanayi")
    hl : str
        언어(host language) 설정. "tr" = 터키어
    gl : str
        지역(geo location) 설정. "TR" = 터키
    lookback_days : int
        최근 며칠 이내 뉴스만 검색할지 (기본 30일)
    """
    time_filter = _google_news_time_filter_suffix(lookback_days)
    cleaned = " ".join((query or "").split())
    # 이미 when: 옵션이 있으면 중복 추가하지 않습니다.
    if "when:" not in cleaned.lower():
        query_with_time = f"{cleaned} {time_filter}".strip()
    else:
        query_with_time = cleaned
    encoded_query = quote_plus(query_with_time)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


def _news_api_search_params(now: datetime | None = None) -> dict:
    """
    News API 등 `q`/`from`/`sortBy` 파라미터를 쓰는 외부 API용 헬퍼입니다.
    (현재 주 수집 경로는 Google News RSS이지만, 동일 정책으로 맞출 때 사용합니다.)

    Returns
    -------
    dict
        {
          "q": "(otomotiv OR araç OR otomobil OR TOGG)",
          "from": "YYYY-MM-DD",   # 오늘 기준 30일 전
          "sortBy": "publishedAt",
          "language": "tr",
        }
    """
    reference = now if now is not None else datetime.now()
    from_date = _lookback_cutoff(reference).strftime("%Y-%m-%d")
    return {
        "q": NEWS_API_AUTOMOTIVE_QUERY,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "tr",
    }


# 하위 호환 별칭 (이전 이름)
def _news_api_time_params(now: datetime | None = None) -> dict:
    """_news_api_search_params 의 하위 호환 래퍼."""
    return _news_api_search_params(now)


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


def _as_naive_datetime(dt: datetime) -> datetime:
    """timezone-aware datetime을 naive(로컬)로 맞춰 비교가 깨지지 않게 합니다."""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _parse_datetime_value(value) -> datetime | None:
    """
    RSS/API/캐시에서 오는 다양한 발행일 표현을 datetime으로 파싱합니다.
    파싱 실패 시 None (→ 이후 필터에서 drop).
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return _as_naive_datetime(value)

    if isinstance(value, struct_time):
        try:
            return datetime(*value[:6])
        except Exception:
            return None

    # feedparser의 published_parsed는 보통 time.struct_time이지만
    # 튜플/리스트로 들어오는 경우도 대비합니다.
    if isinstance(value, (tuple, list)) and len(value) >= 6:
        try:
            return datetime(*[int(v) for v in value[:6]])
        except Exception:
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text or text in {"날짜 미상", "N/A", "n/a", "-"}:
        return None

    # ISO-8601 (published_at 저장 형식 포함)
    iso_candidate = text.replace("Z", "+00:00")
    try:
        return _as_naive_datetime(datetime.fromisoformat(iso_candidate))
    except Exception:
        pass

    # 흔한 표시/RSS 문자열 포맷
    text_candidates = [text]
    if len(text) >= 19:
        text_candidates.append(text[:19])
    if len(text) >= 16:
        text_candidates.append(text[:16])
    if len(text) >= 10:
        text_candidates.append(text[:10])

    for candidate in text_candidates:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d %b %Y %H:%M:%S",
            "%d %b %Y",
            "%b %d, %Y",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
        ):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue

    # RFC 2822 등 (예: Mon, 04 Aug 2026 10:30:00 GMT)
    try:
        return _as_naive_datetime(parsedate_to_datetime(text))
    except Exception:
        return None


def _entry_published_datetime(entry) -> datetime | None:
    """
    RSS entry에서 발행 시각을 datetime으로 파싱합니다.
    published_parsed → updated_parsed → published/updated 문자열 순으로 시도합니다.
    여러 값이 있으면 '더 오래된 쪽'을 채택합니다.
    (재색인으로 updated만 최근인 오래된 기사를 걸러내기 위함)
    """
    candidates = []
    for key in ("published_parsed", "updated_parsed"):
        parsed = _parse_datetime_value(entry.get(key))
        if parsed is not None:
            candidates.append(parsed)
    for key in ("published", "updated"):
        parsed = _parse_datetime_value(entry.get(key))
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        return None
    return min(candidates)


def _format_published_date(entry) -> str:
    """
    RSS 항목의 발행 일시를 화면 표시용 문자열로 통일합니다.
    시각 정보가 있으면 'YYYY-MM-DD HH:MM', 없으면 'YYYY-MM-DD'.
    """
    dt = _entry_published_datetime(entry)
    if dt is not None:
        if dt.hour or dt.minute or dt.second:
            return dt.strftime("%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d")
    return "날짜 미상"


def _is_within_lookback(published_at: datetime | None, now: datetime | None = None) -> bool:
    """
    발행 시각이 오늘 기준 최근 NEWS_LOOKBACK_DAYS일 이내인지 판별합니다.
    발행일이 없거나 컷오프보다 과거면 False (반드시 drop 대상).
    """
    if published_at is None:
        return False
    reference = now if now is not None else datetime.now()
    cutoff = reference - timedelta(days=NEWS_LOOKBACK_DAYS)
    # 미래로 너무 튀는 이상값도 제외 (시계/파싱 오류 방어)
    if published_at > reference + timedelta(days=1):
        return False
    return published_at >= cutoff


def _news_item_published_datetime(item: dict) -> datetime | None:
    """수집/번역된 뉴스 dict에서 발행 시각을 꺼냅니다."""
    if not isinstance(item, dict):
        return None
    for key in ("published_at", "date", "published", "publishedAt"):
        parsed = _parse_datetime_value(item.get(key))
        if parsed is not None:
            return parsed
    return None


def _drop_news_older_than_lookback(news_list: list, now: datetime | None = None) -> list:
    """
    ★ 핵심 이중 필터: API/RSS가 오래된 기사를 잘못 섞어 줘도
    Python에서 발행일을 다시 검사해 30일보다 과거인 항목은 과감하게 삭제합니다.
    발행일을 파싱할 수 없는 항목도 삭제합니다.
    """
    reference = now if now is not None else datetime.now()
    kept = []
    for item in news_list or []:
        published_at = _news_item_published_datetime(item)
        if _is_within_lookback(published_at, now=reference):
            # 정렬/재필터용으로 published_at을 항상 정규화해 둡니다.
            normalized = dict(item)
            normalized["published_at"] = published_at.isoformat(timespec="seconds")
            if not normalized.get("date") or normalized.get("date") == "날짜 미상":
                if published_at.hour or published_at.minute or published_at.second:
                    normalized["date"] = published_at.strftime("%Y-%m-%d %H:%M")
                else:
                    normalized["date"] = published_at.strftime("%Y-%m-%d")
            kept.append(normalized)
    return kept


def _sort_news_newest_first(news_list: list) -> list:
    """수집된 뉴스를 발행 시각 내림차순(최신순)으로 정렬합니다."""
    return sorted(
        news_list,
        key=lambda item: item.get("published_at")
        or item.get("date")
        or "",
        reverse=True,
    )


def _finalize_news_list(news_list: list, max_total: int | None = None, now: datetime | None = None) -> list:
    """
    수집 결과를 최종 형태로 정리합니다.
    1) 30일 초과 drop  2) 링크 중복 제거  3) 최신순 정렬  4) 상위 N개
    """
    filtered = _drop_news_older_than_lookback(news_list, now=now)
    unique = _dedupe_news_by_link(_sort_news_newest_first(filtered))
    if max_total is None:
        return unique
    return unique[:max_total]


def _dedupe_news_by_link(news_list: list) -> list:
    """동일 링크(또는 제목) 기사는 한 번만 남깁니다. 입력 순서(이미 최신순)를 유지합니다."""
    seen = set()
    unique = []
    for item in news_list:
        key = (item.get("link") or "").strip() or (
            item.get("title_original") or item.get("title_kr") or ""
        ).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


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
def collect_raw_news_for_topic(
    topic_key: str,
    query: str,
    max_results: int = DEFAULT_MAX_ARTICLES_PER_TOPIC,
    as_of_date: str = "",
    cache_version: str = NEWS_CACHE_VERSION,
):
    """
    주제 1개에 대해 구글 뉴스 RSS를 조회하고, 번역하기 전 '원문 그대로'의
    기사 정보를 정리해서 리스트로 반환합니다.

    - Google News 검색에 when:30d 를 붙여 최근 30일 기사만 요청
    - ★ 파싱된 발행일로 Python에서 한 번 더 필터링 (30일 초과는 drop)
    - 최신 발행순으로 정렬 후 상위 max_results개만 반환

    as_of_date / cache_version:
        캐시 키에 날짜·버전을 넣어 오래된/이전 주제 캐시가 재사용되지 않게 합니다.

    반환되는 각 항목의 형태:
        {
            "title_original": "원문 제목",
            "summary_original": "원문 요약(가능하면)",
            "link": "기사 원문(또는 구글 뉴스 경유) 링크",
            "source": "언론사 이름",
            "date": "YYYY-MM-DD HH:MM" (발행 일시),
            "published_at": "ISO 발행 시각 (정렬용)",
        }
    """
    # 캐시 버스트용 인자 (본문 로직에는 직접 쓰지 않음)
    _ = (as_of_date, cache_version)

    now = datetime.now()
    url = _build_google_news_rss_url(query, lookback_days=NEWS_LOOKBACK_DAYS)
    entries = _fetch_rss_entries(url)

    results = []
    for entry in entries:
        published_at = _entry_published_datetime(entry)
        # ★ RSS가 when:30d를 무시하고 오래된 기사를 줘도 Python에서 즉시 drop
        if not _is_within_lookback(published_at, now=now):
            continue

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
                "published_at": published_at.isoformat(timespec="seconds"),
            }
        )

    # 주제 단위에서도 한 번 더 drop → 최신순 → 상위 N
    return _finalize_news_list(results, max_total=max_results, now=now)


def collect_all_raw_news(
    max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC,
    max_total: int = MAX_NEWS_FOR_TRANSLATION,
):
    """
    NEWS_TOPICS(자동차 산업)를 모두 순회하면서 원문 기사를 수집하고,
    각 기사에 "category"(한글 주제명)를 붙인 뒤,
    ★ 30일 초과 drop → 중복 제거 → 전역 최신순 → 상위 max_total개만 반환합니다.
    (이 상위 N개만 Gemini 번역 함수로 전달됩니다.)
    """
    as_of_date = datetime.now().strftime("%Y-%m-%d")
    all_news = []
    for topic in NEWS_TOPICS:
        topic_news = collect_raw_news_for_topic(
            topic["key"],
            topic["query"],
            max_per_topic,
            as_of_date=as_of_date,
            cache_version=NEWS_CACHE_VERSION,
        )
        for item in topic_news:
            item_with_category = dict(item)
            item_with_category["category"] = topic["label_kr"]
            all_news.append(item_with_category)

    # ★ 전역 이중 필터: 주제별 캐시/병합 과정에서 섞인 오래된 기사도 최종 drop
    return _finalize_news_list(all_news, max_total=max_total)


# =============================================================================
# 3. AI 번역/요약 (Google Gemini REST API — SDK 미사용, requests 직접 호출)
# -----------------------------------------------------------------------------
# google-generativeai SDK는 Streamlit Cloud에서 버전 호환성 문제로 "404 model
# not found" 등 오류를 자주 일으켜, 완전히 제거하고 REST API를 requests로
# 직접 호출하는 방식으로 전환했습니다.
#
# 엔드포인트: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}
# Headers   : {"Content-Type": "application/json"}
# Payload   : {"contents": [{"parts": [{"text": "..."}]}], "generationConfig": {...}}
#
# System Instruction 자리에는 "한국인 비즈니스/제조업 경영진이 읽기 편한 전문적인
# 어투로 터키어/영어 뉴스를 한국어로 번역 및 요약"하도록 지시합니다.
# =============================================================================
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_REQUEST_TIMEOUT_SECONDS = 30

# 사용 모델: gemini-3.5-flash (구형 1.5-flash / flash-latest / pro 대체)
GEMINI_MODEL_NAME = "gemini-3.5-flash"
GEMINI_MODEL_CANDIDATES = (
    "gemini-3.5-flash",
)
# 구형(gemini-pro 등) 전용 호출 경로. 현재는 3.5-flash만 사용하므로 비워 둡니다.
_LEGACY_GEMINI_MODELS = frozenset()

# 예시 파일에 들어 있는 자리표시자 값. 이런 값이 secrets에 있으면
# "키가 설정된 것처럼" 보이지만 실제 API 호출은 실패합니다.
_PLACEHOLDER_API_KEYS = {
    "",
    "your-gemini-api-key-here",
    "YOUR_GEMINI_API_KEY",
    "xxxxxxxx",
    "xxx",
}

# Gemini REST API의 systemInstruction(또는 legacy 모델은 본문)으로 전달되는 지시문입니다.
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


class GeminiHttpError(RuntimeError):
    """
    Gemini REST API가 200이 아닌 상태 코드를 반환했을 때 사용하는 예외.
    status_code와 원본 응답 본문(response_text)을 그대로 보관해,
    디버깅 화면에 "날것" 그대로 보여줄 수 있게 합니다.
    """

    def __init__(self, status_code: int, response_text: str, model_name: str):
        message = f"HTTP {status_code} ({model_name}): {response_text}"
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.model_name = model_name


def _is_rate_limit_error(exc: Exception) -> bool:
    """예외 메시지가 429 / quota / rate limit 인지 판별합니다."""
    if getattr(exc, "status_code", None) == 429:
        return True
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
    if getattr(exc, "status_code", None) == 404:
        return True
    text = str(exc).lower()
    return (
        "404" in text
        or ("not found" in text and "model" in text)
        or "is not found" in text
    )


def _build_gemini_rest_payload(model_name: str, user_prompt: str) -> dict:
    """
    Gemini REST API(generateContent) 요청 본문을 만듭니다.

    - gemini-3.5-flash: systemInstruction + response_mime_type(JSON)을 사용해
      번역 지시와 사용자 프롬프트를 분리합니다.
    - 구형 legacy 모델: systemInstruction/JSON mime을 지원하지 않을 수 있어
      지시문을 본문(contents)에 합쳐서 단순하게 요청합니다.
    """
    is_legacy = model_name in _LEGACY_GEMINI_MODELS

    if is_legacy:
        contents_text = (
            f"{TRANSLATION_SYSTEM_PROMPT}\n\n{user_prompt}\n\n"
            "중요: 응답은 위에서 지정한 JSON 형식만 출력하세요."
        )
        payload = {
            "contents": [{"parts": [{"text": contents_text}]}],
            "generationConfig": {"temperature": 0.3},
        }
    else:
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": TRANSLATION_SYSTEM_PROMPT}]},
            "generationConfig": {
                "temperature": 0.3,
                "response_mime_type": "application/json",
            },
        }
    return payload


def _extract_rest_response_text(data: dict) -> str:
    """Gemini REST API의 JSON 응답에서 생성된 텍스트를 안전하게 꺼냅니다."""
    try:
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            chunks = [part.get("text", "") for part in parts if part.get("text")]
            if chunks:
                return "\n".join(chunks).strip()
    except Exception:
        pass
    return ""


def _show_gemini_debug_error(model_name: str, status_code: int, response_text: str) -> None:
    """
    [디버깅 모드] Gemini REST API 호출 실패 시, 원인을 바로 파악할 수 있도록
    응답 원문(response.text)을 뭉뚱그리지 않고 화면에 그대로 출력합니다.
    """
    try:
        st.error(
            f"🔧 [디버그] Gemini REST API 오류 — 모델: `{model_name}` · HTTP {status_code}\n\n"
            f"```\n{response_text}\n```"
        )
    except Exception:
        # Streamlit 실행 컨텍스트 밖(단위 테스트 등)에서는 조용히 무시합니다.
        pass


def _call_gemini_rest_once(api_key: str, model_name: str, user_prompt: str) -> str:
    """
    Gemini REST API(v1beta generateContent)를 requests로 1회 직접 호출합니다.
    SDK(google-generativeai)를 전혀 사용하지 않습니다.
    """
    url = f"{GEMINI_API_BASE_URL}/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = _build_gemini_rest_payload(model_name, user_prompt)

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        # 네트워크 계층 오류(타임아웃/연결 실패 등)도 원문 그대로 보여줍니다.
        _show_gemini_debug_error(model_name, 0, f"{type(exc).__name__}: {exc}")
        raise

    if response.status_code != 200:
        # ★ 요청사항: 실패 시 API가 반환한 실제 에러 메시지를 화면에 날것 그대로 출력
        _show_gemini_debug_error(model_name, response.status_code, response.text)
        raise GeminiHttpError(response.status_code, response.text, model_name)

    try:
        data = response.json()
    except ValueError:
        _show_gemini_debug_error(model_name, response.status_code, response.text)
        raise RuntimeError(f"Gemini 응답을 JSON으로 해석하지 못했습니다: {response.text[:500]}")

    return _extract_rest_response_text(data)


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


def _raise_rate_limit(exc: Exception):
    """429/쿼터 예외를 분당/일일 종류에 맞는 GeminiRateLimitError로 변환해 올립니다."""
    if _is_daily_quota_error(exc):
        raise GeminiRateLimitError(API_DAILY_QUOTA_MESSAGE, kind="daily") from exc
    raise GeminiRateLimitError(API_RATE_LIMIT_MESSAGE, kind="minute") from exc


def _call_gemini_once(api_key: str, user_prompt: str) -> str:
    """
    Gemini REST API를 순서대로 호출해 텍스트 응답을 반환합니다.
    (google-generativeai SDK는 사용하지 않고, requests로 직접 통신합니다.)

    사용 모델: gemini-3.5-flash
    (후보가 여러 개일 경우 404 = 모델 인식 실패일 때만 다음으로 우회)
    429/일일 한도 오류는 즉시 중단합니다(추가 폴백 호출을 하지 않음).

    각 호출이 실패하면 _call_gemini_rest_once() 내부에서
    st.error()로 원본 응답을 그대로 화면에 출력합니다(디버깅 모드).
    """
    last_error = None

    for index, model_name in enumerate(GEMINI_MODEL_CANDIDATES):
        try:
            if index > 0:
                time.sleep(0.5)  # 폴백 호출 사이 최소 대기
            raw_text = _call_gemini_rest_once(api_key, model_name, user_prompt)
            if raw_text:
                return raw_text
            last_error = RuntimeError(f"모델({model_name})이 빈 응답을 반환했습니다.")
        except GeminiRateLimitError:
            raise
        except GeminiHttpError as exc:
            last_error = exc
            if _is_rate_limit_error(exc):
                _raise_rate_limit(exc)
            if _is_model_not_found_error(exc) and index < len(GEMINI_MODEL_CANDIDATES) - 1:
                # 404(모델 인식 실패)일 때만 다음 후보로 우회합니다.
                continue
            break
        except requests.exceptions.RequestException as exc:
            # 네트워크 계층 오류는 폴백하지 않고 바로 실패 처리합니다.
            last_error = exc
            break

    raise RuntimeError(API_TRANSLATION_BUSY_MESSAGE) from last_error


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
    """Gemini/네트워크 예외 메시지를 사용자가 조치하기 쉬운 한글 안내로 바꿉니다."""
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
    if API_TRANSLATION_BUSY_MESSAGE in text:
        return API_TRANSLATION_BUSY_MESSAGE

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
    # 모델 404 / 서버 통신 / 기타 영어 에러는 모두 짧은 한글 안내로 통일합니다.
    # (실제 원인 파악용 원문은 호출 시점에 st.error()로 이미 출력됩니다 — 디버깅 모드)
    if (
        _is_model_not_found_error(exc)
        or "gemini" in lowered
        or "deadline" in lowered
        or "unavailable" in lowered
        or "connection" in lowered
        or "timeout" in lowered
    ):
        return API_TRANSLATION_BUSY_MESSAGE

    # 남은 영문 예외도 화면에 그대로 노출하지 않습니다.
    has_hangul = any("가" <= ch <= "힣" for ch in text)
    if text and not has_hangul:
        return API_TRANSLATION_BUSY_MESSAGE
    return text if text else API_TRANSLATION_BUSY_MESSAGE


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
    """
    보관 중인 마지막 성공 번역을 반환합니다.
    ★ 반환 직전에도 30일 초과 기사를 drop해, 예전 캐시에 2012/2월 기사가
    남아 있어도 화면에 나오지 않게 합니다.
    """
    store = _last_good_news_store()
    news = store.get("news") or []
    if not news:
        return []
    return _finalize_news_list(list(news), max_total=MAX_NEWS_FOR_TRANSLATION)


def _raw_news_as_display_items(raw_news_list: list) -> list:
    """
    Gemini 없이 RSS 원문만으로 화면 표시용 항목을 만듭니다.
    일일 한도 초과 시에도 '가짜 더미' 대신 실제 최신 기사 링크를 보여줍니다.
    """
    # 표시 직전에도 한 번 더 30일 필터(이중 방어)
    filtered = _finalize_news_list(raw_news_list, max_total=MAX_NEWS_FOR_TRANSLATION)
    display_items = []
    for raw in filtered:
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
                "published_at": raw.get("published_at", ""),
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
    우선순위: 마지막 성공 번역(30일 재필터) → RSS 원문 → 빈 목록(앱에서 더미로 대체).
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
# 성공한 번역 결과만 @st.cache_data(ttl=12시간)으로 캐시합니다.
# 429/일일 한도 실패는 예외로 올리되, fetch 단계에서 쿨다운을 걸어
# 새로고침해도 Gemini를 다시 호출하지 않습니다.
# 번역은 기사별 개별 호출이 아니라 배치 1~2회로 RPM 제한을 피합니다.
# =============================================================================
@st.cache_data(
    ttl=CACHE_TTL_SECONDS,
    show_spinner="터키 자동차 산업 뉴스를 수집하고 Gemini로 번역하는 중입니다...",
)
def _cached_ai_translated_news(
    max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC,
    cache_version: str = NEWS_CACHE_VERSION,
):
    """성공한 뉴스 리스트만 캐시합니다. 실패 시 NewsFetchError를 발생시킵니다."""
    _ = cache_version  # 주제/필터 변경 시 캐시 강제 갱신
    try:
        api_key = _get_gemini_api_key()
        if not api_key:
            raise NewsFetchError(
                "GEMINI_API_KEY가 설정되지 않았거나 예시 값(your-gemini-api-key-here) 그대로입니다."
            )

        raw_news_list = collect_all_raw_news(max_per_topic=max_per_topic)
        # ★ 번역 직전 최종 이중 필터: 진짜 한 달 이내 + 최신순만 Gemini로 전달
        raw_news_list = _finalize_news_list(raw_news_list, max_total=MAX_NEWS_FOR_TRANSLATION)
        if not raw_news_list:
            raise NewsFetchError(
                "최근 30일 이내의 터키 자동차 산업 기사를 구글 뉴스 RSS에서 찾지 못했습니다. "
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
                    "published_at": raw.get("published_at", ""),
                }
            )

        # 번역 후에도 날짜 기준으로 한 번 더 정리(캐시/이상값 방어)
        translated_news = _finalize_news_list(translated_news, max_total=MAX_NEWS_FOR_TRANSLATION)
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
        news = _cached_ai_translated_news(
            max_per_topic=max_per_topic,
            cache_version=NEWS_CACHE_VERSION,
        )
        # 성공해도 반환 직전 한 번 더 30일 필터(캐시된 이상값 방어)
        news = _finalize_news_list(news, max_total=MAX_NEWS_FOR_TRANSLATION)
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
        # 일반 실패(모델 404 소진, 통신 오류 등)도 화면이 비지 않도록
        # 이전 번역 캐시 → RSS 원문 순으로 대체합니다.
        return _fallback_news_payload(
            error_message=str(exc),
            error_kind="other",
            max_per_topic=max_per_topic,
        )
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
        return _fallback_news_payload(
            error_message=_humanize_gemini_error(exc),
            error_kind="other",
            max_per_topic=max_per_topic,
        )


def get_ai_translated_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """
    하위 호환용 함수. 뉴스 리스트만 필요할 때 사용합니다.
    실패 시 빈 리스트를 반환합니다.
    """
    return fetch_ai_translated_news(max_per_topic=max_per_topic)["news"]