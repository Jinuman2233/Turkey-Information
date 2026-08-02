# =============================================================================
# news_crawler.py
# -----------------------------------------------------------------------------
# 이 파일은 "실시간 터키 뉴스 자동 수집 + AI 한국어 번역" 기능을 담당합니다.
#
# 전체 흐름 (아래로 갈수록 더 구체적인 작업입니다):
#   1) feedparser로 구글 뉴스(Google News) RSS에서 터키 관련 기사 5개 주제를 수집
#   2) 각 기사의 제목/요약(원문, 보통 영어 또는 터키어)을 정리
#   3) OpenAI API(또는 Gemini API)를 이용해 한국어로 번역 + 3줄 요약
#   4) 결과를 Streamlit 캐시(@st.cache_data, 12시간)에 저장해서
#      같은 12시간 안에는 API를 다시 호출하지 않도록 함 (비용 절감 + 속도 향상)
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
# 이 모듈은 아래 두 가지 방법 중 편한 방법으로 API 키를 읽어옵니다.
# (둘 다 설정하지 않으면, AI 번역 기능은 자동으로 비활성화되고 더미 뉴스가 대신 표시됩니다.)
#
# [방법 1] .env 파일 사용 (로컬 개발 환경에 추천)
#   1. 프로젝트 최상위 폴더(이 파일과 같은 위치의 상위 폴더)에 ".env" 파일을 만듭니다.
#   2. 아래처럼 한 줄을 적어줍니다. (실제 발급받은 키로 교체)
#        OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
#   3. ".env" 파일은 절대 GitHub 등에 올리면 안 되므로, .gitignore에 이미 등록해 두었습니다.
#
# [방법 2] Streamlit secrets.toml 사용 (Streamlit Community Cloud 배포 시 추천)
#   1. 프로젝트의 ".streamlit/secrets.toml" 파일(.streamlit/secrets.toml.example 참고)에
#      아래처럼 적어줍니다.
#        OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#   2. Streamlit Community Cloud에 배포할 때는 "App settings > Secrets" 메뉴에
#      동일한 내용을 붙여넣으면 됩니다.
#
# [선택] OpenAI 대신 Gemini를 사용하고 싶다면
#   - AI_PROVIDER 값을 "gemini"로 설정하고, GEMINI_API_KEY를 위와 동일한 방식으로 설정하세요.
#   - Gemini 사용 시에는 `pip install google-genai` 로 패키지를 추가 설치해야 합니다.
# =============================================================================

import os
import re
import json
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

# openai 패키지 (OpenAI API 호출용). 설치되어 있지 않으면 None으로 두고,
# 실제로 OpenAI를 사용하려고 할 때에만 에러 메시지를 보여줍니다.
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# google-genai 패키지 (Gemini API 호출용, 선택 사항).
# AI_PROVIDER="gemini"로 설정했을 때만 필요하며, 기본값(OpenAI)만 쓴다면
# 설치하지 않아도 전혀 문제가 없습니다.
try:
    from google import genai as google_genai
except ImportError:
    google_genai = None


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
CACHE_TTL_SECONDS = 60 * 60 * 12  # 12시간 (문제에서 요구한 캐시 유효시간)


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
# 3. AI 번역/요약 (OpenAI API 기본, Gemini API 선택 가능)
# -----------------------------------------------------------------------------
# 프롬프트(지시문)에는 "비즈니스 및 제조업 경영진이 읽기 편한 전문적이고
# 명확한 어투로 번역할 것"이라는 요구사항을 반드시 포함시켰습니다.
# =============================================================================
OPENAI_MODEL_NAME = "gpt-4o-mini"  # 번역/요약처럼 비교적 단순한 작업에 적합한 저비용 모델
GEMINI_MODEL_NAME = "gemini-2.0-flash"  # Gemini를 사용할 경우의 저비용/고속 모델

TRANSLATION_SYSTEM_PROMPT = """당신은 터키에 진출한 한국 기업의 경영진을 위해 현지 뉴스를 번역·요약하는
전문 비즈니스 번역가입니다.

아래 규칙을 반드시 지켜서 번역/요약해 주세요.
1. 비즈니스 및 제조업 경영진이 읽기 편한, 전문적이고 명확한 어투로 번역할 것 (구어체, 과장된 표현 금지)
2. 원문에 없는 내용을 추측해서 추가하지 말 것
3. 응답은 반드시 아래 JSON 형식 그대로만 출력할 것 (그 외 설명 문장 금지)

{"title_kr": "번역된 한국어 제목", "summary_kr": ["요약 문장1", "요약 문장2", "요약 문장3"]}
"""


def _build_user_prompt(title_original: str, summary_original: str) -> str:
    return (
        f"[원문 제목]\n{title_original}\n\n"
        f"[원문 요약/본문]\n{summary_original or '(제공된 요약이 없어 제목만으로 판단해야 합니다)'}\n\n"
        "위 뉴스 기사를 한국어로 번역하고, 핵심 내용을 정확히 3줄로 요약해 주세요."
    )


def _parse_translation_response(raw_text: str, fallback_title: str):
    """
    AI가 돌려준 텍스트(JSON 형식)를 파싱합니다.
    혹시 JSON 형식이 아니거나 파싱에 실패하면, 원문 제목과 안내 문구로
    안전하게 대체(fallback)해서 화면이 깨지지 않도록 합니다.
    """
    try:
        data = json.loads(raw_text)
        title_kr = str(data.get("title_kr") or fallback_title).strip()
        summary_kr = data.get("summary_kr")
        if not isinstance(summary_kr, list) or len(summary_kr) == 0:
            summary_kr = [str(summary_kr or "요약 내용을 생성하지 못했습니다.")]
        # 3줄을 넘으면 앞의 3개만 사용하고, 3줄이 안 되면 있는 만큼만 사용합니다.
        summary_kr = [str(line).strip() for line in summary_kr[:3] if str(line).strip()]
        if not summary_kr:
            summary_kr = ["요약 내용을 생성하지 못했습니다."]
        return title_kr, summary_kr
    except Exception:
        return fallback_title, ["⚠️ AI 응답을 해석하지 못해 요약을 표시할 수 없습니다."]


def _translate_with_openai(api_key: str, title_original: str, summary_original: str):
    """OpenAI Chat Completions API를 호출해서 번역/요약 결과를 받아옵니다."""
    if OpenAI is None:
        raise RuntimeError(
            "openai 패키지가 설치되어 있지 않습니다. `pip install openai` 명령으로 설치해 주세요."
        )

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        messages=[
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(title_original, summary_original)},
        ],
        # response_format을 JSON으로 강제하면 AI가 항상 정해진 형식으로만 답하도록 유도할 수 있습니다.
        response_format={"type": "json_object"},
        temperature=0.3,  # 낮을수록 더 일관되고 정확한(창의성이 낮은) 번역 결과를 얻습니다.
    )
    raw_text = response.choices[0].message.content
    return _parse_translation_response(raw_text, fallback_title=title_original)


def _translate_with_gemini(api_key: str, title_original: str, summary_original: str):
    """Google Gemini API를 호출해서 번역/요약 결과를 받아옵니다. (OpenAI의 대안)"""
    if google_genai is None:
        raise RuntimeError(
            "google-genai 패키지가 설치되어 있지 않습니다. `pip install google-genai` 명령으로 설치해 주세요."
        )

    client = google_genai.Client(api_key=api_key)
    prompt = f"{TRANSLATION_SYSTEM_PROMPT}\n\n{_build_user_prompt(title_original, summary_original)}"
    response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=prompt)

    # Gemini는 JSON 강제 옵션 없이도 대체로 지시한 형식을 잘 따르지만,
    # 혹시 앞뒤에 ```json ... ``` 같은 코드블록 표시가 붙어 나오는 경우를 대비해 제거해 줍니다.
    raw_text = (response.text or "").strip()
    raw_text = re.sub(r"^```(json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
    return _parse_translation_response(raw_text, fallback_title=title_original)


def _get_ai_provider() -> str:
    """
    사용할 AI 제공자를 결정합니다. ("openai" 또는 "gemini")
    secrets.toml 또는 환경변수(.env)의 AI_PROVIDER 값을 읽고, 없으면 기본값인 "openai"를 사용합니다.
    """
    value = _read_config_value("AI_PROVIDER")
    return (value or "openai").strip().lower()


def _read_config_value(key: str):
    """
    Streamlit secrets.toml -> .env/환경변수 순서로 설정값을 찾아주는 공통 함수.
    두 곳 모두에 없으면 None을 반환합니다.
    """
    try:
        # secrets.toml 파일 자체가 없는 프로젝트에서는 st.secrets 접근 시 예외가 발생할 수 있으므로
        # try-except로 감싸서 앱이 멈추지 않도록 합니다.
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key)


def _get_api_key_for_provider(provider: str):
    key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    return _read_config_value(key_name)


def is_ai_translation_configured() -> bool:
    """
    화면(app.py)에서 'AI 번역 기능을 쓸 수 있는지'를 미리 확인할 때 사용하는 함수입니다.
    API 키가 설정되어 있지 않으면 False를 반환하고, app.py는 이때 더미 뉴스로 대체합니다.
    """
    provider = _get_ai_provider()
    return bool(_get_api_key_for_provider(provider))


def _translate_and_summarize(provider: str, api_key: str, title_original: str, summary_original: str):
    """provider 값에 따라 OpenAI 또는 Gemini 번역 함수를 호출하는 공통 진입점."""
    if provider == "gemini":
        return _translate_with_gemini(api_key, title_original, summary_original)
    return _translate_with_openai(api_key, title_original, summary_original)


# =============================================================================
# 4. 최종 공개 함수 — app.py에서는 이 함수 하나만 호출하면 됩니다.
# -----------------------------------------------------------------------------
# @st.cache_data(ttl=43200)를 적용해서, 한 번 번역한 결과는 12시간 동안 그대로
# 재사용합니다. 이렇게 하면
#   1) 사용자가 새로고침할 때마다 매번 OpenAI/Gemini API를 호출하지 않아도 되어
#      "API 호출 비용"이 크게 절감되고,
#   2) 이미 계산된 결과를 즉시 보여주므로 "대시보드 로딩 속도"도 빨라집니다.
# =============================================================================
@st.cache_data(
    ttl=CACHE_TTL_SECONDS,
    show_spinner="최신 터키 뉴스를 수집하고 AI로 한국어 번역하는 중입니다... (최대 1분 정도 걸릴 수 있어요)",
)
def get_ai_translated_news(max_per_topic: int = DEFAULT_MAX_ARTICLES_PER_TOPIC):
    """
    5가지 주제에 대한 최신 터키 뉴스를 수집한 뒤, AI로 한국어 번역/요약까지
    완료한 결과를 리스트로 반환합니다.

    반환되는 각 뉴스 항목의 형태 (modules/news_data.py의 더미 데이터와 동일한 구조):
        {
            "category": "무역·관세",
            "title_kr": "번역된 한국어 제목",
            "summary_kr": ["요약1", "요약2", "요약3"],
            "link": "원문 기사 링크",
            "source": "언론사 이름",
            "date": "YYYY-MM-DD",
        }

    API 키가 설정되어 있지 않거나, 기사 수집/번역에 실패하면 빈 리스트([])를
    반환합니다. app.py에서는 빈 리스트가 반환되면 더미 뉴스를 대신 보여줍니다.
    """
    provider = _get_ai_provider()
    api_key = _get_api_key_for_provider(provider)

    if not api_key:
        return []

    raw_news_list = collect_all_raw_news(max_per_topic=max_per_topic)
    if not raw_news_list:
        return []

    translated_news = []
    for raw in raw_news_list:
        try:
            title_kr, summary_kr = _translate_and_summarize(
                provider, api_key, raw["title_original"], raw["summary_original"]
            )
        except Exception:
            # 특정 기사 하나의 번역이 실패(API 오류, 요금 한도 초과 등)하더라도
            # 전체 뉴스 목록이 통째로 실패하지 않도록 해당 기사만 건너뜁니다.
            continue

        translated_news.append(
            {
                "category": raw["category"],
                "title_kr": title_kr,
                "summary_kr": summary_kr,
                "link": raw["link"],
                "source": raw["source"],
                "date": raw["date"],
            }
        )

    return translated_news
