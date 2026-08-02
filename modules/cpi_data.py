# =============================================================================
# cpi_data.py
# -----------------------------------------------------------------------------
# 터키 소비자물가지수(TÜFE / CPI)와 연간(YoY)·월간(MoM) 물가상승률을 제공합니다.
#
# 공식 출처:
#   터키 통계청 (TÜİK, Türkiye İstatistik Kurumu)이 발표하는 소비자물가지수(TÜFE)
#
# 수집 우선순위:
#   1) TCMB 웹페이지에 재공표된 TÜİK TÜFE 월별 표 (가장 최신 반영)
#   2) FRED TURCPIALLMINMEI (TÜİK 기반 지수, 시차가 있을 수 있음)
#   3) TÜİK가 발표한 최근 실측치를 반영한 오프라인 폴백(더미)
#
# 금속산업 노무 협상 참고:
#   MESS(금속산업 사용자협회) ↔ Türk Metal(금속노조) 단체협약의
#   물가상승분(enflasyon farkı) / 임금 조정 기준으로 활용됩니다.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta

# -----------------------------------------------------------------------------
# 상수
# -----------------------------------------------------------------------------
FRED_CPI_TICKER = "TURCPIALLMINMEI"
FETCH_LOOKBACK_MONTHS = 84
DISPLAY_MONTHS = 36
RECENT_MOM_MONTHS = 12
CACHE_TTL_SECONDS = 60 * 60 * 24  # 하루(86400초)

OFFICIAL_SOURCE_LABEL = "터키 통계청 (TÜİK, Türkiye İstatistik Kurumu) — TÜFE"
LABOR_NEGOTIATION_NOTE = (
    "💡 본 데이터는 TÜİK 공식 발표 자료이며, MESS(터키 금속산업 사용자협회)와 "
    "Türk Metal(터키 금속노조) 간 단체협약(Toplu İş Sözleşmesi)의 "
    "물가상승분(enflasyon farkı) 반영 및 임금 조정 기준으로 사용됩니다."
)

# TCMB가 TÜİK 발표치를 표로 재공표하는 페이지 (TR / EN)
TCMB_TUFE_URLS = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari",
    "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Statistics/Inflation+Data/Consumer+Prices",
)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TurkeyBusinessDashboard/1.0; "
        "+https://github.com/Jinuman2233/Turkey-Information)"
    )
}

# -----------------------------------------------------------------------------
# TÜİK 공식 발표치 기반 오프라인 폴백 (YYYY-MM → YoY%, MoM%)
# TCMB/TÜİK 공개 표(2023-01 ~ 2026-06)를 반영. API 실패 시에도
# 올해(2026) 최신 월까지 실제 흐름을 보여주기 위한 값입니다.
# -----------------------------------------------------------------------------
TUFE_OFFICIAL_FALLBACK: dict[str, dict[str, float]] = {
    "2023-01": {"yoy": 57.68, "mom": 6.65},
    "2023-02": {"yoy": 55.18, "mom": 3.15},
    "2023-03": {"yoy": 50.51, "mom": 2.29},
    "2023-04": {"yoy": 43.68, "mom": 2.39},
    "2023-05": {"yoy": 39.59, "mom": 0.04},
    "2023-06": {"yoy": 38.21, "mom": 3.92},
    "2023-07": {"yoy": 47.83, "mom": 9.49},
    "2023-08": {"yoy": 58.94, "mom": 9.09},
    "2023-09": {"yoy": 61.53, "mom": 4.75},
    "2023-10": {"yoy": 61.36, "mom": 3.43},
    "2023-11": {"yoy": 61.98, "mom": 3.28},
    "2023-12": {"yoy": 64.77, "mom": 2.93},
    "2024-01": {"yoy": 64.86, "mom": 6.70},
    "2024-02": {"yoy": 67.07, "mom": 4.53},
    "2024-03": {"yoy": 68.50, "mom": 3.16},
    "2024-04": {"yoy": 69.80, "mom": 3.18},
    "2024-05": {"yoy": 75.45, "mom": 3.37},
    "2024-06": {"yoy": 71.60, "mom": 1.64},
    "2024-07": {"yoy": 61.78, "mom": 3.23},
    "2024-08": {"yoy": 51.97, "mom": 2.47},
    "2024-09": {"yoy": 49.38, "mom": 2.97},
    "2024-10": {"yoy": 48.58, "mom": 2.88},
    "2024-11": {"yoy": 47.09, "mom": 2.24},
    "2024-12": {"yoy": 44.38, "mom": 1.03},
    "2025-01": {"yoy": 42.12, "mom": 5.03},
    "2025-02": {"yoy": 39.05, "mom": 2.27},
    "2025-03": {"yoy": 38.10, "mom": 2.46},
    "2025-04": {"yoy": 37.86, "mom": 3.00},
    "2025-05": {"yoy": 35.41, "mom": 1.53},
    "2025-06": {"yoy": 35.05, "mom": 1.37},
    "2025-07": {"yoy": 33.52, "mom": 2.06},
    "2025-08": {"yoy": 32.95, "mom": 2.04},
    "2025-09": {"yoy": 33.29, "mom": 3.23},
    "2025-10": {"yoy": 32.87, "mom": 2.55},
    "2025-11": {"yoy": 31.07, "mom": 0.87},
    "2025-12": {"yoy": 30.89, "mom": 0.89},
    "2026-01": {"yoy": 30.65, "mom": 4.84},
    "2026-02": {"yoy": 31.53, "mom": 2.96},
    "2026-03": {"yoy": 30.87, "mom": 1.94},
    "2026-04": {"yoy": 32.37, "mom": 4.18},
    "2026-05": {"yoy": 32.61, "mom": 1.71},
    "2026-06": {"yoy": 32.11, "mom": 0.99},
}


def _empty_result(is_dummy: bool = True, source: str = "dummy") -> dict:
    """실패 시에도 동일한 키 구조를 유지하기 위한 빈 결과."""
    return {
        "df": pd.DataFrame(columns=["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"]),
        "latest_yoy": None,
        "latest_mom": None,
        "yoy_change": None,
        "latest_month": None,
        "is_dummy": is_dummy,
        "source": source,
        "source_label": OFFICIAL_SOURCE_LABEL,
        "labor_note": LABOR_NEGOTIATION_NOTE,
    }


def _month_key_to_timestamp(month_key: str) -> pd.Timestamp:
    """'YYYY-MM' 또는 'MM-YYYY' 문자열을 월초 Timestamp로 변환합니다."""
    text = str(month_key).strip()
    for fmt in ("%Y-%m", "%m-%Y", "%Y/%m", "%m/%Y"):
        try:
            return pd.Timestamp(datetime.strptime(text, fmt).replace(day=1))
        except ValueError:
            continue
    # 숫자만 있는 경우 등 — pandas에 위임
    ts = pd.to_datetime(text, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"연월 형식을 해석할 수 없습니다: {month_key}")
    return pd.Timestamp(ts).replace(day=1)


def _rates_dict_to_frame(rates: dict[str, dict[str, float]]) -> pd.DataFrame:
    """YoY/MoM dict를 화면용 DataFrame으로 변환하고, MoM으로 CPI 지수를 재구성합니다."""
    if not rates:
        return pd.DataFrame(columns=["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"])

    rows = []
    for month_key, values in rates.items():
        rows.append(
            {
                "날짜": _month_key_to_timestamp(month_key),
                "연월": _month_key_to_timestamp(month_key).strftime("%Y-%m"),
                "YoY(%)": float(values["yoy"]),
                "MoM(%)": float(values["mom"]),
            }
        )

    frame = pd.DataFrame(rows).sort_values("날짜").reset_index(drop=True)

    # 임금 협상 참고용으로 MoM을 누적해 상대 CPI 지수를 만듭니다. (기준=100)
    cpi_values = []
    level = 100.0
    for idx, mom in enumerate(frame["MoM(%)"]):
        if idx == 0:
            cpi_values.append(level)
        else:
            level = level * (1.0 + float(mom) / 100.0)
            cpi_values.append(level)
    frame["CPI"] = cpi_values
    return frame[["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"]].tail(DISPLAY_MONTHS).reset_index(drop=True)


def _compute_inflation_frame_from_index(cpi: pd.Series) -> pd.DataFrame:
    """CPI 지수 시계열로부터 YoY/MoM을 계산합니다 (FRED 폴백용)."""
    cpi = cpi.dropna().astype(float).sort_index()
    if cpi.empty:
        return pd.DataFrame(columns=["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"])

    yoy = (cpi / cpi.shift(12) - 1.0) * 100.0
    mom = (cpi / cpi.shift(1) - 1.0) * 100.0
    frame = pd.DataFrame(
        {
            "날짜": cpi.index,
            "CPI": cpi.values,
            "YoY(%)": yoy.values,
            "MoM(%)": mom.values,
        }
    )
    frame = frame.dropna(subset=["YoY(%)", "MoM(%)"]).tail(DISPLAY_MONTHS).copy()
    frame["연월"] = pd.to_datetime(frame["날짜"]).dt.strftime("%Y-%m")
    return frame[["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"]].reset_index(drop=True)


def _summarize(frame: pd.DataFrame, is_dummy: bool, source: str) -> dict:
    """차트/카드/테이블용 요약 dict를 만듭니다."""
    if frame.empty:
        return _empty_result(is_dummy=is_dummy, source=source)

    latest_yoy = float(frame["YoY(%)"].iloc[-1])
    latest_mom = float(frame["MoM(%)"].iloc[-1])
    prev_yoy = float(frame["YoY(%)"].iloc[-2]) if len(frame) >= 2 else latest_yoy
    yoy_change = latest_yoy - prev_yoy

    return {
        "df": frame,
        "latest_yoy": latest_yoy,
        "latest_mom": latest_mom,
        "yoy_change": yoy_change,
        "latest_month": str(frame["연월"].iloc[-1]),
        "is_dummy": is_dummy,
        "source": source,
        "source_label": OFFICIAL_SOURCE_LABEL,
        "labor_note": LABOR_NEGOTIATION_NOTE,
    }


def _normalize_tcmb_table(raw: pd.DataFrame) -> pd.DataFrame:
    """TCMB HTML 표의 컬럼명을 표준화하고 YoY/MoM frame으로 변환합니다."""
    if raw is None or raw.empty:
        raise RuntimeError("TCMB TÜFE 표가 비어 있습니다.")

    df = raw.copy()
    # 첫 컬럼이 연월인 경우가 많음 (Unnamed: 0 / Ay-Yıl)
    if df.columns[0] not in df.columns[1:]:
        df = df.rename(columns={df.columns[0]: "month"})
    else:
        df.columns = ["month"] + [f"col_{i}" for i in range(1, len(df.columns))]

    colmap = {}
    for col in df.columns:
        name = str(col).lower()
        if col == "month" or "ay-yıl" in name or "ay-yil" in name:
            colmap[col] = "month"
        elif "yıllık" in name or "yillik" in name or "year to year" in name:
            colmap[col] = "yoy"
        elif "aylık" in name or "aylik" in name or "month to month" in name:
            colmap[col] = "mom"
    df = df.rename(columns=colmap)

    if not {"month", "yoy", "mom"}.issubset(df.columns):
        raise RuntimeError(f"TCMB 표 컬럼을 해석하지 못했습니다: {list(raw.columns)}")

    rates: dict[str, dict[str, float]] = {}
    for _, row in df.iterrows():
        try:
            month_ts = _month_key_to_timestamp(row["month"])
            yoy = float(row["yoy"])
            mom = float(row["mom"])
        except (TypeError, ValueError):
            continue
        rates[month_ts.strftime("%Y-%m")] = {"yoy": yoy, "mom": mom}

    if len(rates) < 12:
        raise RuntimeError("TCMB에서 파싱된 TÜFE 행이 부족합니다.")

    return _rates_dict_to_frame(rates)


def _fetch_tcmb_tuik_frame() -> pd.DataFrame:
    """
    TCMB 페이지에서 TÜİK TÜFE(YoY/MoM) 표를 파싱합니다.
    터키 통계청 공식 발표치를 중앙은행이 재공표한 최신 표입니다.
    """
    last_error = None
    for url in TCMB_TUFE_URLS:
        try:
            response = requests.get(url, timeout=20, headers=HTTP_HEADERS)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError("HTML 표를 찾지 못했습니다.")
            # 가장 행이 많은 표를 TÜFE 시계열로 간주
            candidate = max(tables, key=lambda t: len(t))
            return _normalize_tcmb_table(candidate)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"TCMB TÜİK TÜFE 수집 실패: {last_error}")


def _fetch_fred_frame() -> pd.DataFrame:
    """FRED 터키 CPI 지수로 YoY/MoM을 계산합니다 (시차 발생 가능)."""
    from pandas_datareader import data as web

    end = datetime.today()
    start = end - relativedelta(months=FETCH_LOOKBACK_MONTHS)
    raw = web.DataReader(FRED_CPI_TICKER, "fred", start, end)
    if raw is None or raw.empty:
        raise RuntimeError("FRED에서 빈 CPI 데이터를 반환했습니다.")

    series = raw[FRED_CPI_TICKER].dropna()
    if series.empty:
        raise RuntimeError("FRED CPI 시리즈에 유효한 값이 없습니다.")
    series = series.copy()
    series.name = "CPI"
    frame = _compute_inflation_frame_from_index(series)
    if frame.empty or len(frame) < 12:
        raise RuntimeError("FRED 기반 CPI 시계열이 너무 짧습니다.")
    return frame


def _build_official_fallback_frame() -> pd.DataFrame:
    """API 실패 시 TÜİK 공식 발표 실측치를 반영한 폴백 frame."""
    return _rates_dict_to_frame(TUFE_OFFICIAL_FALLBACK)


def _latest_month_key(frame: pd.DataFrame) -> str:
    return str(frame["연월"].iloc[-1])


def _load_turkey_cpi_uncached() -> dict:
    """
    최신 TÜİK TÜFE가 최대한 반영되도록 소스 우선순위로 로드합니다.
    여러 소스가 성공하면 '가장 최근 월'이 더 새로운 쪽을 선택합니다.
    """
    candidates: list[tuple[pd.DataFrame, str, bool]] = []

    try:
        candidates.append(
            (
                _fetch_tcmb_tuik_frame(),
                "TÜİK TÜFE (TCMB 재공표)",
                False,
            )
        )
    except Exception:
        pass

    try:
        candidates.append(
            (
                _fetch_fred_frame(),
                f"FRED:{FRED_CPI_TICKER} (TÜİK 기반, 시차 가능)",
                False,
            )
        )
    except Exception:
        pass

    try:
        candidates.append(
            (
                _build_official_fallback_frame(),
                "TÜİK 공식 발표치 기반 오프라인 폴백",
                True,
            )
        )
    except Exception:
        pass

    if not candidates:
        return _empty_result(is_dummy=True, source="unavailable")

    # 최신 연월이 가장 늦은 소스를 선택 (동률이면 앞선=더 공식에 가까운 소스 유지)
    best_frame, best_source, best_dummy = candidates[0]
    best_month = _latest_month_key(best_frame)
    for frame, source, is_dummy in candidates[1:]:
        month = _latest_month_key(frame)
        if month > best_month:
            best_frame, best_source, best_dummy, best_month = frame, source, is_dummy, month

    return _summarize(best_frame, is_dummy=best_dummy, source=best_source)


def get_recent_mom_table(cpi_df: pd.DataFrame, months: int = RECENT_MOM_MONTHS) -> pd.DataFrame:
    """
    최근 N개월 MoM 테이블을 가로형(열이 연-월)으로 반환합니다.
    임금 인상률 계산 시 월별 누적 변동을 한눈에 보기 위한 형태입니다.
    """
    if cpi_df is None or cpi_df.empty:
        return pd.DataFrame()

    recent = cpi_df.tail(months).copy()
    wide = pd.DataFrame(
        [recent["MoM(%)"].map(lambda v: round(float(v), 2)).tolist()],
        index=["전월 대비 물가상승률 (MoM %)"],
        columns=recent["연월"].tolist(),
    )
    wide.columns.name = "연-월 (Year-Month)"
    return wide


def get_recent_mom_vertical_table(
    cpi_df: pd.DataFrame, months: int = RECENT_MOM_MONTHS
) -> pd.DataFrame:
    """최근 N개월 MoM을 세로형(행=연월) 표로 반환합니다."""
    if cpi_df is None or cpi_df.empty:
        return pd.DataFrame(columns=["연-월 (Year-Month)", "전월 대비 물가상승률 (MoM %)"])

    recent = cpi_df.tail(months).copy()
    return pd.DataFrame(
        {
            "연-월 (Year-Month)": recent["연월"].tolist(),
            "전월 대비 물가상승률 (MoM %)": recent["MoM(%)"].map(lambda v: round(float(v), 2)).tolist(),
        }
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_turkey_cpi_data() -> dict:
    """
    터키 TÜİK TÜFE 3년(36개월) 추이 + 핵심 지표를 반환합니다.
    하루(86400초)에 한 번만 원천 데이터를 갱신합니다.
    """
    return _load_turkey_cpi_uncached()
