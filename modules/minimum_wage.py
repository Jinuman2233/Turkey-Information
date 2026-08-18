# =============================================================================
# minimum_wage.py
# -----------------------------------------------------------------------------
# 터키 세전 최저임금(Gross Asgari Ücret)을 웹에서 자동 수집하고,
# 최근 5년(2022~2026) 시간당 Gross 최저임금의 TRY/EUR/USD 추이 차트를 제공합니다.
#
# [현재값 수집 우선순위]
#   1) 터키 노동사회보장부(CSGB) 공식 Asgari Ücret 페이지
#   2) TradingEconomics — Turkey Gross Minimum Monthly Wage
#   3) 현지/전문 경제 포털(CottGroup 등) 보조 파싱
#   4) 실패 시 2026년 최신 기준 세전 금액 폴백
#
# [5년 추이]
#   - 정부 발표 월 Gross 변경 시점(2022~2026)을 월별 step 시계열로 구성
#   - 시간당 Gross = 월 Gross ÷ 255시간
#   - yfinance 월평균 EUR/TRY·USD/TRY로 EUR·USD 환산
#   - 통신 실패 시 FALLBACK mock 환율/임금으로 시각화
# =============================================================================

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup
from plotly.subplots import make_subplots

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
# -----------------------------------------------------------------------------
FALLBACK_GROSS_WAGE_TRY = 33_030.0
FALLBACK_NET_WAGE_TRY = 28_075.50
FALLBACK_EFFECTIVE_YEAR = 2026
FALLBACK_EFFECTIVE_MONTH = 1

# -----------------------------------------------------------------------------
# 최근 5년(2022~2026) 터키 정부 발표 월 Gross 최저임금 변경 시점
# (공식 brüt asgari ücret — 반기/연간 개정 모두 포함)
# -----------------------------------------------------------------------------
OFFICIAL_GROSS_WAGE_PERIODS = [
    {
        "start": "2022-01",
        "end": "2022-06",
        "monthly_gross_try": 5_004.0,
        "monthly_net_try": 4_253.40,
    },
    {
        "start": "2022-07",
        "end": "2022-12",
        "monthly_gross_try": 6_471.0,
        "monthly_net_try": 5_500.35,
    },
    {
        "start": "2023-01",
        "end": "2023-06",
        "monthly_gross_try": 10_008.0,
        "monthly_net_try": 8_506.80,
    },
    {
        "start": "2023-07",
        "end": "2023-12",
        "monthly_gross_try": 13_414.50,
        "monthly_net_try": 11_402.32,
    },
    {
        "start": "2024-01",
        "end": "2024-12",
        "monthly_gross_try": 20_002.50,
        "monthly_net_try": 17_002.12,
    },
    {
        "start": "2025-01",
        "end": "2025-12",
        "monthly_gross_try": 26_005.50,
        "monthly_net_try": 22_104.67,
    },
    {
        "start": "2026-01",
        "end": "2026-12",
        "monthly_gross_try": 33_030.0,
        "monthly_net_try": 28_075.50,
    },
]

# 통신 실패 시 사용할 월평균 EUR/TRY · USD/TRY mock (대략적 역사 평균)
FALLBACK_MONTHLY_FX: dict[str, dict[str, float]] = {
    "2022-01": {"EURTRY": 15.35, "USDTRY": 13.55},
    "2022-02": {"EURTRY": 15.55, "USDTRY": 13.70},
    "2022-03": {"EURTRY": 16.05, "USDTRY": 14.55},
    "2022-04": {"EURTRY": 16.10, "USDTRY": 14.70},
    "2022-05": {"EURTRY": 16.55, "USDTRY": 15.55},
    "2022-06": {"EURTRY": 17.85, "USDTRY": 17.00},
    "2022-07": {"EURTRY": 17.95, "USDTRY": 17.55},
    "2022-08": {"EURTRY": 18.20, "USDTRY": 18.05},
    "2022-09": {"EURTRY": 18.05, "USDTRY": 18.25},
    "2022-10": {"EURTRY": 18.15, "USDTRY": 18.55},
    "2022-11": {"EURTRY": 19.15, "USDTRY": 18.60},
    "2022-12": {"EURTRY": 19.80, "USDTRY": 18.65},
    "2023-01": {"EURTRY": 20.25, "USDTRY": 18.80},
    "2023-02": {"EURTRY": 20.25, "USDTRY": 18.85},
    "2023-03": {"EURTRY": 20.50, "USDTRY": 19.00},
    "2023-04": {"EURTRY": 21.35, "USDTRY": 19.40},
    "2023-05": {"EURTRY": 21.55, "USDTRY": 19.75},
    "2023-06": {"EURTRY": 25.55, "USDTRY": 23.40},
    "2023-07": {"EURTRY": 29.35, "USDTRY": 26.75},
    "2023-08": {"EURTRY": 29.45, "USDTRY": 26.95},
    "2023-09": {"EURTRY": 28.85, "USDTRY": 27.00},
    "2023-10": {"EURTRY": 28.75, "USDTRY": 27.75},
    "2023-11": {"EURTRY": 31.25, "USDTRY": 28.70},
    "2023-12": {"EURTRY": 32.15, "USDTRY": 29.05},
    "2024-01": {"EURTRY": 32.85, "USDTRY": 30.05},
    "2024-02": {"EURTRY": 33.35, "USDTRY": 30.85},
    "2024-03": {"EURTRY": 34.85, "USDTRY": 32.05},
    "2024-04": {"EURTRY": 34.55, "USDTRY": 32.25},
    "2024-05": {"EURTRY": 34.85, "USDTRY": 32.25},
    "2024-06": {"EURTRY": 35.25, "USDTRY": 32.75},
    "2024-07": {"EURTRY": 35.85, "USDTRY": 32.95},
    "2024-08": {"EURTRY": 37.25, "USDTRY": 33.65},
    "2024-09": {"EURTRY": 37.95, "USDTRY": 34.05},
    "2024-10": {"EURTRY": 37.15, "USDTRY": 34.25},
    "2024-11": {"EURTRY": 36.55, "USDTRY": 34.45},
    "2024-12": {"EURTRY": 36.65, "USDTRY": 34.90},
    "2025-01": {"EURTRY": 37.25, "USDTRY": 35.45},
    "2025-02": {"EURTRY": 37.85, "USDTRY": 35.95},
    "2025-03": {"EURTRY": 38.55, "USDTRY": 36.55},
    "2025-04": {"EURTRY": 39.15, "USDTRY": 37.05},
    "2025-05": {"EURTRY": 39.75, "USDTRY": 37.55},
    "2025-06": {"EURTRY": 40.35, "USDTRY": 38.05},
    "2025-07": {"EURTRY": 40.95, "USDTRY": 38.55},
    "2025-08": {"EURTRY": 41.55, "USDTRY": 39.05},
    "2025-09": {"EURTRY": 42.15, "USDTRY": 39.55},
    "2025-10": {"EURTRY": 42.65, "USDTRY": 40.05},
    "2025-11": {"EURTRY": 43.15, "USDTRY": 40.55},
    "2025-12": {"EURTRY": 43.65, "USDTRY": 41.05},
    "2026-01": {"EURTRY": 44.25, "USDTRY": 41.65},
    "2026-02": {"EURTRY": 44.75, "USDTRY": 42.15},
    "2026-03": {"EURTRY": 45.25, "USDTRY": 42.65},
    "2026-04": {"EURTRY": 45.75, "USDTRY": 43.15},
    "2026-05": {"EURTRY": 46.25, "USDTRY": 43.65},
    "2026-06": {"EURTRY": 46.75, "USDTRY": 44.15},
    "2026-07": {"EURTRY": 47.25, "USDTRY": 44.65},
    "2026-08": {"EURTRY": 47.75, "USDTRY": 45.15},
}


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

    cleaned = (
        raw.replace("₺", "")
        .replace("TL", "")
        .replace("TRY", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )
    cleaned = re.sub(r"[^0-9,\.]", "", cleaned)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2 and len(parts[0]) <= 3:
            if len(parts[0]) > 3:
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        value = float(cleaned)
    except ValueError:
        return None

    if 5_000 <= value <= 200_000:
        return value
    return None


def _parse_effective_date(text: str) -> tuple[int, int] | None:
    """본문에서 적용 시작일(YYYY-MM)을 찾아 (year, month)로 반환합니다."""
    if not text:
        return None

    patterns = [
        r"01[./]01[./](20\d{2})",
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

            for table in soup.find_all("table"):
                for row in table.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
                    if len(cells) < 2:
                        continue
                    label = cells[0].upper()
                    value = _parse_tr_number(cells[1])
                    if value is None:
                        continue
                    if "NET" in label and "ASGARİ" in label.replace("I", "İ"):
                        net = value
                    elif re.search(r"ASGAR[İI]\s*ÜCRET", label) and "NET" not in label:
                        if gross is None:
                            gross = value

            if gross is None:
                brut_match = re.search(
                    r"BR[ÜU]T\s+ASGAR[İI]\s+ÜCRET\s*([0-9\.,]+)",
                    page_text,
                    flags=re.IGNORECASE,
                )
                if brut_match:
                    gross = _parse_tr_number(brut_match.group(1))

            if gross is None:
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
        for match in re.finditer(r"\b(33[\s\.,]?030(?:[.,]00)?)\b", text):
            gross = _parse_tr_number(match.group(1))
            if gross is not None:
                break

    if gross is None:
        raise RuntimeError("TradingEconomics에서 Gross 최저임금을 찾지 못했습니다.")

    date_info = _parse_effective_date(text)
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

    return _fallback_info(reason="; ".join(errors)[:180] or "all_sources_failed")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_minimum_wage_info() -> dict:
    """
    터키 세전(Gross) 최저임금 정보를 반환합니다.
    하루(86400초)에 한 번만 웹에서 갱신합니다.
    """
    try:
        return _fetch_minimum_wage_uncached()
    except Exception:
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


# =============================================================================
# 최근 5년 시간당 Gross 최저임금 추이 (TRY / EUR / USD)
# =============================================================================
def _month_range(start: str = "2022-01", end: str | None = None) -> list[pd.Timestamp]:
    """YYYY-MM 문자열 구간의 월 시작일 리스트를 만듭니다."""
    start_ts = pd.Timestamp(f"{start}-01")
    if end is None:
        end_ts = pd.Timestamp(datetime.now().strftime("%Y-%m-01"))
    else:
        end_ts = pd.Timestamp(f"{end}-01")
    if end_ts < start_ts:
        end_ts = start_ts
    return list(pd.date_range(start=start_ts, end=end_ts, freq="MS"))


def _monthly_gross_try_series(months: list[pd.Timestamp]) -> pd.Series:
    """공식 변경 시점을 step-fill 하여 월별 월 Gross(TRY) 시계열을 만듭니다."""
    values = []
    for month_ts in months:
        key = month_ts.strftime("%Y-%m")
        wage = None
        for period in OFFICIAL_GROSS_WAGE_PERIODS:
            if period["start"] <= key <= period["end"]:
                wage = float(period["monthly_gross_try"])
                break
        if wage is None:
            # 범위 밖이면 가장 가까운 이전 기간 값
            for period in reversed(OFFICIAL_GROSS_WAGE_PERIODS):
                if key >= period["start"]:
                    wage = float(period["monthly_gross_try"])
                    break
        values.append(wage if wage is not None else FALLBACK_GROSS_WAGE_TRY)
    return pd.Series(values, index=pd.DatetimeIndex(months), name="monthly_gross_try")


def _fallback_fx_frame(months: list[pd.Timestamp]) -> pd.DataFrame:
    """하드코딩 mock 월평균 환율 프레임."""
    rows = []
    last_fx = {"EURTRY": 45.0, "USDTRY": 42.0}
    for month_ts in months:
        key = month_ts.strftime("%Y-%m")
        fx = FALLBACK_MONTHLY_FX.get(key) or last_fx
        last_fx = fx
        rows.append(
            {
                "month": month_ts,
                "EURTRY": float(fx["EURTRY"]),
                "USDTRY": float(fx["USDTRY"]),
            }
        )
    return pd.DataFrame(rows).set_index("month")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_monthly_fx_averages(start: str = "2022-01-01", end: str | None = None) -> pd.DataFrame | None:
    """
    yfinance로 EURTRY·USDTRY 일봉을 받아 월평균 환율을 계산합니다.
    실패 시 None.
    """
    try:
        end_date = end or datetime.now().strftime("%Y-%m-%d")
        raw = yf.download(
            ["EURTRY=X", "USDTRY=X"],
            start=start,
            end=end_date,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if raw is None or raw.empty:
            return None

        # yfinance multi-index columns: ('Close', 'EURTRY=X') 형태
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].copy()
        else:
            close = raw[["Close"]].copy() if "Close" in raw.columns else raw.copy()

        rename_map = {}
        for col in close.columns:
            name = str(col)
            if "EURTRY" in name:
                rename_map[col] = "EURTRY"
            elif "USDTRY" in name:
                rename_map[col] = "USDTRY"
        close = close.rename(columns=rename_map)

        needed = [c for c in ("EURTRY", "USDTRY") if c in close.columns]
        if len(needed) < 2:
            return None

        monthly = close[needed].astype(float).resample("MS").mean().dropna(how="any")
        if monthly.empty:
            return None
        return monthly
    except Exception:
        return None


def _build_trend_dataframe(
    monthly_hours: float = MONTHLY_WORKING_HOURS,
    use_live_fx: bool = True,
) -> tuple[pd.DataFrame, bool, str]:
    """
    월별 시간당 Gross (TRY/EUR/USD) + TRY 인상률(%) 데이터프레임을 만듭니다.

    Returns
    -------
    (df, is_fx_fallback, source_note)
    """
    hours = monthly_hours if monthly_hours and monthly_hours > 0 else MONTHLY_WORKING_HOURS
    months = _month_range("2022-01")
    monthly_gross = _monthly_gross_try_series(months)
    hourly_try = monthly_gross / float(hours)

    fx_source = "yfinance:monthly_avg"
    is_fx_fallback = False
    live_fx = _fetch_monthly_fx_averages("2022-01-01") if use_live_fx else None
    mock_fx = _fallback_fx_frame(months)

    if live_fx is None or live_fx.empty:
        fx_df = mock_fx
        fx_source = "fallback:mock_monthly_fx"
        is_fx_fallback = True
    else:
        live = live_fx.copy()
        live.index = pd.to_datetime(live.index).to_period("M").to_timestamp()
        fx_df = mock_fx.copy()
        for col in ("EURTRY", "USDTRY"):
            if col in live.columns:
                fx_df[col] = live[col].reindex(fx_df.index)
                if fx_df[col].isna().any():
                    is_fx_fallback = True
                fx_df[col] = fx_df[col].fillna(mock_fx[col])
        fx_source = (
            "mixed:yfinance+fallback" if is_fx_fallback else "yfinance:monthly_avg"
        )

    aligned = pd.DataFrame(
        {
            "monthly_gross_try": monthly_gross.values,
            "hourly_gross_try": hourly_try.values,
        },
        index=pd.DatetimeIndex(months, name="month"),
    )
    aligned = aligned.join(fx_df[["EURTRY", "USDTRY"]], how="left")
    aligned["EURTRY"] = aligned["EURTRY"].ffill().bfill()
    aligned["USDTRY"] = aligned["USDTRY"].ffill().bfill()

    aligned["hourly_gross_eur"] = aligned["hourly_gross_try"] / aligned["EURTRY"]
    aligned["hourly_gross_usd"] = aligned["hourly_gross_try"] / aligned["USDTRY"]
    aligned["raise_pct"] = aligned["hourly_gross_try"].pct_change() * 100.0
    aligned["raise_pct"] = aligned["raise_pct"].fillna(0.0)

    return aligned.reset_index(), is_fx_fallback, fx_source


def _figure_from_trend_df(df: pd.DataFrame) -> go.Figure:
    """추이 데이터프레임으로 Plotly 다중 라인 차트를 생성합니다."""
    raise_labels = []
    for value in df["raise_pct"]:
        if pd.notna(value) and float(value) > 0.05:
            raise_labels.append(f"+{float(value):.1f}%")
        else:
            raise_labels.append("")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=df["month"],
            y=df["hourly_gross_try"],
            name="시간당 Gross (TRY)",
            mode="lines+markers+text",
            line=dict(color="#C8102E", width=3),
            marker=dict(size=8, color="#C8102E"),
            text=raise_labels,
            textposition="top center",
            textfont=dict(size=11, color="#8B0000"),
            hovertemplate=(
                "%{x|%Y-%m}<br>"
                "TRY: ₺%{y:.2f}/h<br>"
                "인상률: %{customdata:.1f}%<extra></extra>"
            ),
            customdata=df["raise_pct"],
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["month"],
            y=df["hourly_gross_eur"],
            name="시간당 Gross (EUR)",
            mode="lines+markers",
            line=dict(color="#1565C0", width=2.5),
            marker=dict(size=6, color="#1565C0"),
            hovertemplate="%{x|%Y-%m}<br>EUR: €%{y:.3f}/h<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=df["month"],
            y=df["hourly_gross_usd"],
            name="시간당 Gross (USD)",
            mode="lines+markers",
            line=dict(color="#2E7D32", width=2.5, dash="dot"),
            marker=dict(size=6, color="#2E7D32"),
            hovertemplate="%{x|%Y-%m}<br>USD: $%{y:.3f}/h<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        margin=dict(t=18, b=6, l=8, r=8),
        height=180,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        autosize=True,
    )
    fig.update_xaxes(title_text="연-월", tickformat="%Y-%m", dtick="M3")
    fig.update_yaxes(title_text="시간당 Gross (TRY)", secondary_y=False)
    fig.update_yaxes(title_text="시간당 Gross (EUR / USD)", secondary_y=True, showgrid=False)
    return fig


def build_hourly_gross_wage_trend_figure(
    monthly_hours: float = MONTHLY_WORKING_HOURS,
) -> go.Figure:
    """
    TRY(주축) + EUR/USD(보조축) 시간당 Gross 최저임금 다중 꺾은선 차트.
    TRY 마커 위에 이전 시점 대비 인상률(%) 텍스트를 표시합니다.
    """
    df, _, _ = _build_trend_dataframe(monthly_hours=monthly_hours, use_live_fx=True)
    return _figure_from_trend_df(df)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="최저임금 5년 추이·월평균 환율을 준비하는 중입니다...")
def _cached_hourly_gross_trend_frame(
    monthly_hours: float = MONTHLY_WORKING_HOURS,
) -> tuple[pd.DataFrame, bool, str]:
    """추이 데이터프레임만 하루 캐시합니다 (Figure는 캐시하지 않음)."""
    return _build_trend_dataframe(monthly_hours=monthly_hours, use_live_fx=True)


def get_hourly_gross_wage_trend(
    monthly_hours: float = MONTHLY_WORKING_HOURS,
) -> dict:
    """
    대시보드용 5년 추이 패키지.

    Returns
    -------
    dict
        {
          "dataframe": pd.DataFrame,
          "figure": plotly Figure,
          "is_fx_fallback": bool,
          "source": str,
        }
    """
    df, is_fx_fallback, fx_source = _cached_hourly_gross_trend_frame(monthly_hours)
    figure = _figure_from_trend_df(df)
    return {
        "dataframe": df,
        "figure": figure,
        "is_fx_fallback": is_fx_fallback,
        "source": (
            "공식 Gross 변경시점(2022~2026) + "
            f"월평균 환율({fx_source}) · 시간당 = 월 Gross ÷ {int(monthly_hours)}시간"
        ),
    }
