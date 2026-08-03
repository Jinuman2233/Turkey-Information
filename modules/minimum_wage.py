# =============================================================================
# minimum_wage.py
# -----------------------------------------------------------------------------
# 터키 세전 최저임금(Gross Asgari Ücret)을 웹에서 자동 수집합니다.
#
# 수집 우선순위:
#   1) 터키 노동사회보장부(CSGB) 공식 Asgari Ücret 페이지
#   2) TradingEconomics — Turkey Gross Minimum Monthly Wage
#   3) 현지/전문 경제 포털(CottGroup 등) 보조 파싱
#   4) 실패 시 2026년 최신 기준 세전 금액 폴백
#
# 결과는 @st.cache_data(ttl=86400)로 하루 1회만 갱신합니다.
# =============================================================================

from __future__ import annotations

import re
from datetime import datetime

import requests
import streamlit as st
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
# 월 근무시간 기준값 (시간당 최저임금 계산용)
# -----------------------------------------------------------------------------
MONTHLY_WORKING_HOURS = 255
CACHE_TTL_SECONDS = 60 * 60 * 24  # 하루

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TurkeyBusinessDashboard/1.0; "
        "+https://github.com/Jinuman2233/Turkey-Information)"
    )
}

# CSGB 공식 페이지
CSGB_ASGARI_URLS = (
    "https://www.csgb.gov.tr/poco-pages/asgari-ucret/",
    "https://csgb.gov.tr/poco-pages/asgari-ucret/",
)

# 보조 소스
TRADING_ECONOMICS_URL = "https://tradingeconomics.com/turkey/minimum-wages"
COTTGROUP_URL = (
    "https://www.cottgroup.com/en/blog/work-life/item/"
    "what-is-minimum-wage-how-much-is-the-minimum-wage-in-turkiye-2026"
)

# -----------------------------------------------------------------------------
# 안전장치(Fallback): 2026년 최신 기준 세전(Gross) 최저임금
# CSGB 공식 발표: 2026-01-01 적용, 월 Gross 33,030 TRY / Net 28,075.50 TRY
# (사용자 요청의 "약 34,000 TRY" 수준에 가장 가까운 실제 공식 수치)
# -----------------------------------------------------------------------------
FALLBACK_GROSS_WAGE_TRY = 33_030.0
FALLBACK_NET_WAGE_TRY = 28_075.50
FALLBACK_EFFECTIVE_YEAR = 2026
FALLBACK_EFFECTIVE_MONTH = 1


def _fallback_info(reason: str = "crawl_failed") -> dict:
    """크롤링 실패 시에도 화면이 멈추지 않도록 기본값을 반환합니다."""
    return {
        "gross_wage_try": FALLBACK_GROSS_WAGE_TRY,
        "net_wage_try": FALLBACK_NET_WAGE_TRY,
        "effective_year": FALLBACK_EFFECTIVE_YEAR,
        "effective_month": FALLBACK_EFFECTIVE_MONTH,
        "effective_period": (
            f"적용/발표일: {FALLBACK_EFFECTIVE_YEAR}년 {FALLBACK_EFFECTIVE_MONTH:02d}월"
        ),
        "source": f"fallback:{reason}",
        "is_fallback": True,
    }


def _parse_tr_number(text: str) -> float | None:
    """
    터키식 숫자 표기(33.030,00 / 33,030.00 / 33030)를 float로 변환합니다.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    # 통화/공백 제거
    cleaned = (
        raw.replace("₺", "")
        .replace("TL", "")
        .replace("TRY", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )
    # 괄호/기타 문자 제거 후 숫자·구분자만 남김
    cleaned = re.sub(r"[^0-9,\.]", "", cleaned)
    if not cleaned:
        return None

    # 터키식: 33.030,00 → 천단위(.) + 소수(,)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # 33,030 또는 28,075.50 혼재 가능 → 마지막 , 뒤가 2자리면 소수
        parts = cleaned.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2 and len(parts[0]) <= 3:
            # 28,07 같은 소수일 수도 있으나 최저임금은 보통 천단위
            # 천단위 패턴(33,030) 우선
            if len(parts[0]) > 3:
                cleaned = cleaned.replace(",", "")
            else:
                # 애매하면 천단위로 간주(터키 관행)
                cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        value = float(cleaned)
    except ValueError:
        return None

    # 월 최저임금으로 합리적인 범위만 허용 (오탐 방지)
    if 5_000 <= value <= 200_000:
        return value
    return None


def _parse_effective_date(text: str) -> tuple[int, int] | None:
    """본문에서 적용 시작일(YYYY-MM)을 찾아 (year, month)로 반환합니다."""
    if not text:
        return None

    patterns = [
        r"01[./]01[./](20\d{2})",  # 01.01.2026 / 01/01/2026
        r"(20\d{2})\s*[-./]\s*01\s*[-./]\s*01",
        r"(20\d{2})\s*yılı",
        r"effective from January 1,\s*(20\d{2})",
        r"January\s+1,?\s*(20\d{2})",
        r"(20\d{2})\s*년",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            year = int(match.group(1))
            if 2015 <= year <= 2100:
                return year, 1

    # 기간 표기: 01/01/2026 - 31/12/2026
    range_match = re.search(
        r"0?1[./]0?1[./](20\d{2})\s*[-–]\s*\d{1,2}[./]\d{1,2}[./]20\d{2}",
        text,
    )
    if range_match:
        return int(range_match.group(1)), 1

    return None


def _format_effective_period(year: int, month: int) -> str:
    return f"적용/발표일: {year}년 {month:02d}월"


def _http_get(url: str, timeout: int = 20) -> str:
    response = requests.get(url, timeout=timeout, headers=HTTP_HEADERS)
    response.raise_for_status()
    return response.text


def _scrape_csgb() -> dict:
    """터키 노동부(CSGB) 공식 Asgari Ücret 페이지에서 Gross/적용일을 파싱합니다."""
    last_error = None
    for url in CSGB_ASGARI_URLS:
        try:
            html = _http_get(url)
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            gross = None
            net = None

            # 1) 표에서 ASGARİ ÜCRET / NET ASGARİ ÜCRET 행 파싱
            for table in soup.find_all("table"):
                for row in table.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
                    if len(cells) < 2:
                        continue
                    label = cells[0].upper()
                    value = _parse_tr_number(cells[1])
                    if value is None:
                        continue
                    # "NET ASGARİ ÜCRET"가 아닌 순수 ASGARİ ÜCRET = Gross(브뤼트)
                    if "NET" in label and "ASGARİ" in label.replace("I", "İ"):
                        net = value
                    elif re.search(r"ASGAR[İI]\s*ÜCRET", label) and "NET" not in label:
                        # 첫 번째 Gross 값을 채택
                        if gross is None:
                            gross = value

            # 2) 본문 보조: BRÜT ASGARİ ÜCRET 33.030,00
            if gross is None:
                brut_match = re.search(
                    r"BR[ÜU]T\s+ASGAR[İI]\s+ÜCRET\s*([0-9\.,]+)",
                    page_text,
                    flags=re.IGNORECASE,
                )
                if brut_match:
                    gross = _parse_tr_number(brut_match.group(1))

            if gross is None:
                # 표 첫 행 패턴: ASGARİ ÜCRET 33.030,00
                generic = re.search(
                    r"(?<!NET\s)ASGAR[İI]\s+ÜCRET\s*([0-9\.,]+)",
                    page_text,
                    flags=re.IGNORECASE,
                )
                if generic:
                    gross = _parse_tr_number(generic.group(1))

            if gross is None:
                raise RuntimeError("CSGB 페이지에서 Gross 최저임금을 찾지 못했습니다.")

            if net is None:
                net_match = re.search(
                    r"NET\s+ASGAR[İI]\s+ÜCRET\s*([0-9\.,]+)",
                    page_text,
                    flags=re.IGNORECASE,
                )
                if net_match:
                    net = _parse_tr_number(net_match.group(1))

            date_info = _parse_effective_date(page_text)
            year, month = date_info if date_info else (FALLBACK_EFFECTIVE_YEAR, FALLBACK_EFFECTIVE_MONTH)

            return {
                "gross_wage_try": float(gross),
                "net_wage_try": float(net) if net is not None else None,
                "effective_year": int(year),
                "effective_month": int(month),
                "effective_period": _format_effective_period(year, month),
                "source": f"CSGB:{url}",
                "is_fallback": False,
            }
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"CSGB 크롤링 실패: {last_error}")


def _scrape_trading_economics() -> dict:
    """TradingEconomics Turkey Gross Minimum Monthly Wage 페이지를 파싱합니다."""
    html = _http_get(TRADING_ECONOMICS_URL)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    gross = None
    # "Minimum Wages in Turkey increased to 33030 TRY/Month"
    patterns = [
        r"increased to\s*([0-9\.,]+)\s*TRY",
        r"Minimum Wages\s*([0-9\.,]+)\s*[0-9\.,]+\s*TRY/Month",
        r"all time high of\s*([0-9\.,]+)\s*TRY",
        r"Actual[^0-9]*([0-9]{4,6}(?:[.,][0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            gross = _parse_tr_number(match.group(1))
            if gross is not None:
                break

    if gross is None:
        # 페이지에 33030.00 형태가 여러 번 등장
        for match in re.finditer(r"\b(33[\s\.,]?030(?:[.,]00)?)\b", text):
            gross = _parse_tr_number(match.group(1))
            if gross is not None:
                break

    if gross is None:
        raise RuntimeError("TradingEconomics에서 Gross 최저임금을 찾지 못했습니다.")

    date_info = _parse_effective_date(text)
    # TE는 연도 단위 갱신이므로 해당 연도 1월로 표기
    year_match = re.search(r"in\s+(20\d{2})\b", text)
    if date_info:
        year, month = date_info
    elif year_match:
        year, month = int(year_match.group(1)), 1
    else:
        year, month = FALLBACK_EFFECTIVE_YEAR, FALLBACK_EFFECTIVE_MONTH

    return {
        "gross_wage_try": float(gross),
        "net_wage_try": None,
        "effective_year": int(year),
        "effective_month": int(month),
        "effective_period": _format_effective_period(year, month),
        "source": f"TradingEconomics:{TRADING_ECONOMICS_URL}",
        "is_fallback": False,
    }


def _scrape_cottgroup() -> dict:
    """현지 전문 포털(CottGroup) 2026 최저임금 안내 페이지를 파싱합니다."""
    html = _http_get(COTTGROUP_URL)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    gross = None
    net = None

    # 표의 최신 행: 01.01.2026 - 31.12.2026 | ... | 33,030.00
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            if "2026" in cells[0] and len(cells) >= 3:
                value = _parse_tr_number(cells[-1])
                if value is not None:
                    gross = value
                    break
        if gross is not None:
            break

    if gross is None:
        m = re.search(
            r"Monthly Gross Wage:\s*([0-9\.,]+)\s*TRY",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            gross = _parse_tr_number(m.group(1))

    if gross is None:
        raise RuntimeError("CottGroup에서 Gross 최저임금을 찾지 못했습니다.")

    net_match = re.search(
        r"Monthly Net Wage:\s*([0-9\.,]+)\s*TRY",
        text,
        flags=re.IGNORECASE,
    )
    if net_match:
        net = _parse_tr_number(net_match.group(1))

    date_info = _parse_effective_date(text)
    year, month = date_info if date_info else (2026, 1)

    return {
        "gross_wage_try": float(gross),
        "net_wage_try": float(net) if net is not None else None,
        "effective_year": int(year),
        "effective_month": int(month),
        "effective_period": _format_effective_period(year, month),
        "source": f"CottGroup:{COTTGROUP_URL}",
        "is_fallback": False,
    }


def _fetch_minimum_wage_uncached() -> dict:
    """소스 우선순위로 Gross 최저임금을 수집합니다. 모두 실패하면 폴백."""
    scrapers = (
        ("csgb", _scrape_csgb),
        ("trading_economics", _scrape_trading_economics),
        ("cottgroup", _scrape_cottgroup),
    )
    errors: list[str] = []
    for name, scraper in scrapers:
        try:
            result = scraper()
            if result and result.get("gross_wage_try"):
                return result
            errors.append(f"{name}: empty")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    fallback = _fallback_info(reason="; ".join(errors)[:180] or "all_sources_failed")
    return fallback


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_minimum_wage_info() -> dict:
    """
    터키 세전(Gross) 최저임금 정보를 반환합니다.
    하루(86400초)에 한 번만 웹에서 갱신합니다.

    Returns
    -------
    dict
        {
            "gross_wage_try": float,
            "net_wage_try": float | None,
            "effective_year": int,
            "effective_month": int,
            "effective_period": "적용/발표일: YYYY년 MM월",
            "source": str,
            "is_fallback": bool,
        }
    """
    try:
        return _fetch_minimum_wage_uncached()
    except Exception:
        # 어떤 예외가 나와도 대시보드가 죽지 않도록 최종 방어
        return _fallback_info(reason="unexpected_error")


def get_hourly_gross_wage_try(monthly_hours: float = MONTHLY_WORKING_HOURS) -> float:
    """
    월 세전(Gross) 최저임금 ÷ 월 근무시간 으로
    시간당 세전(Gross) 최저임금(TRY)을 계산합니다.
    """
    info = get_minimum_wage_info()
    hours = monthly_hours if monthly_hours and monthly_hours > 0 else MONTHLY_WORKING_HOURS
    return float(info["gross_wage_try"]) / float(hours)


def convert_wage_to_foreign_currencies(wage_try: float, fx_rates: dict) -> dict:
    """
    TRY(터키리라) 금액을 EUR, USD, KRW로 환산합니다.

    Parameters
    ----------
    wage_try : float
        환산하고 싶은 터키리라 금액 (예: 최저임금)
    fx_rates : dict
        modules.fx_rates.get_all_fx_rates() 의 결과값
        {"EURTRY": {...}, "USDTRY": {...}, "TRYKRW": {...}}

    Returns
    -------
    dict
        {"EUR": 값 또는 None, "USD": 값 또는 None, "KRW": 값 또는 None}
    """
    result = {"EUR": None, "USD": None, "KRW": None}

    eurtry = fx_rates.get("EURTRY")
    if eurtry and eurtry.get("current"):
        result["EUR"] = wage_try / eurtry["current"]

    usdtry = fx_rates.get("USDTRY")
    if usdtry and usdtry.get("current"):
        result["USD"] = wage_try / usdtry["current"]

    trykrw = fx_rates.get("TRYKRW")
    if trykrw and trykrw.get("current"):
        result["KRW"] = wage_try * trykrw["current"]

    return result
