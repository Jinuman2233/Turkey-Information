# =============================================================================
# cpi_data.py
# -----------------------------------------------------------------------------
# 터키 소비자물가지수(CPI)와 이로부터 계산한 연간(YoY)·월간(MoM) 물가상승률을
# 제공합니다.
#
# 데이터 출처:
#   - FRED (Federal Reserve Economic Data)
#   - 시리즈 ID: TURCPIALLMINMEI
#     (OECD Main Economic Indicators — Turkey CPI, All Items)
#
# pandas_datareader 로 FRED API를 호출하며, 네트워크/API 실패 시에도
# 대시보드가 멈추지 않도록 최근 3년 추세를 반영한 더미 데이터를 반환합니다.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd
import streamlit as st

# FRED에서 제공하는 터키 CPI(전체 품목) 월별 지수 시리즈
FRED_CPI_TICKER = "TURCPIALLMINMEI"
# YoY 계산에 직전 12개월이 필요하므로, 표시 36개월 + 여유분(리베이스/공백 대비)을 조회합니다.
FETCH_LOOKBACK_MONTHS = 84
DISPLAY_MONTHS = 36
CACHE_TTL_SECONDS = 60 * 60 * 24  # 하루(86400초)


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
    }


def _build_mock_cpi_index(months: int = FETCH_LOOKBACK_MONTHS) -> pd.Series:
    """
    API 실패 시 사용할 현실적인 터키 CPI 지수(더미)를 만듭니다.

    최근 터키 인플레이션은 대략 YoY 40%~80% 구간에 있었으므로,
    월간 MoM을 조절해 그 범위의 YoY가 나오도록 구성합니다.
    """
    # 오늘 기준 월초를 끝점으로, months 개의 월별 시점을 생성합니다.
    end_month = datetime.today().replace(day=1)
    dates = pd.date_range(end=end_month, periods=months, freq="MS")

    # 초반(약 3년 전)은 고물가, 이후 점진적으로 둔화되는 패턴.
    # MoM(%)을 시간에 따라 변화시켜 YoY가 대략 80% → 40% 근처로 내려가게 합니다.
    rng = np.random.default_rng(42)  # 재현 가능한 더미 데이터
    base_mom = np.linspace(4.8, 2.8, months)  # 월 평균 상승률(%)
    noise = rng.normal(0.0, 0.35, size=months)
    mom_pct = np.clip(base_mom + noise, 1.5, 7.0)

    # 시작 지수를 100으로 두고 MoM을 누적해 CPI 지수를 만듭니다.
    index_values = [100.0]
    for mom in mom_pct[1:]:
        index_values.append(index_values[-1] * (1.0 + mom / 100.0))

    return pd.Series(index_values, index=dates, name="CPI")


def _compute_inflation_frame(cpi: pd.Series) -> pd.DataFrame:
    """
    CPI 지수 시계열로부터 YoY(%) / MoM(%)을 계산하고,
    화면 표시용 최근 DISPLAY_MONTHS개월 DataFrame을 반환합니다.
    """
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
    # YoY가 계산된 행만 남긴 뒤, 최근 36개월만 사용합니다.
    frame = frame.dropna(subset=["YoY(%)", "MoM(%)"]).tail(DISPLAY_MONTHS).copy()
    frame["연월"] = pd.to_datetime(frame["날짜"]).dt.strftime("%Y-%m")
    frame = frame.reset_index(drop=True)
    return frame[["날짜", "연월", "CPI", "YoY(%)", "MoM(%)"]]


def _summarize(frame: pd.DataFrame, is_dummy: bool, source: str) -> dict:
    """차트용 DataFrame과 핵심 지표 카드 값을 묶어 반환합니다."""
    if frame.empty:
        return _empty_result(is_dummy=is_dummy, source=source)

    latest_yoy = float(frame["YoY(%)"].iloc[-1])
    latest_mom = float(frame["MoM(%)"].iloc[-1])
    prev_yoy = float(frame["YoY(%)"].iloc[-2]) if len(frame) >= 2 else latest_yoy
    yoy_change = latest_yoy - prev_yoy  # 전월 대비 YoY 변동폭 (%p)

    return {
        "df": frame,
        "latest_yoy": latest_yoy,
        "latest_mom": latest_mom,
        "yoy_change": yoy_change,
        "latest_month": str(frame["연월"].iloc[-1]),
        "is_dummy": is_dummy,
        "source": source,
    }


def _fetch_fred_cpi_series() -> pd.Series:
    """
    pandas_datareader로 FRED 터키 CPI 지수를 가져옵니다.
    실패 시 예외를 그대로 올려 호출부에서 더미로 대체합니다.
    """
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
    return series


def _load_turkey_cpi_uncached() -> dict:
    """캐시 없이 CPI를 로드합니다. 실패 시 더미 데이터로 대체합니다."""
    try:
        cpi_series = _fetch_fred_cpi_series()
        frame = _compute_inflation_frame(cpi_series)
        if frame.empty or len(frame) < 12:
            raise RuntimeError("계산된 CPI 시계열이 너무 짧습니다.")
        return _summarize(frame, is_dummy=False, source=f"FRED:{FRED_CPI_TICKER}")
    except Exception:
        # 네트워크 오류, 패키지 미설치, FRED 장애 등 — 대시보드는 계속 동작해야 합니다.
        mock_series = _build_mock_cpi_index()
        frame = _compute_inflation_frame(mock_series)
        return _summarize(frame, is_dummy=True, source="dummy")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_turkey_cpi_data() -> dict:
    """
    터키 CPI 3년(36개월) 추이 + 핵심 지표를 반환합니다.
    하루(86400초)에 한 번만 원천 데이터를 갱신합니다.

    Returns
    -------
    dict
        {
            "df": DataFrame(날짜, 연월, CPI, YoY(%), MoM(%)),
            "latest_yoy": float | None,
            "latest_mom": float | None,
            "yoy_change": float | None,   # 전월 대비 YoY 변동폭 (%p)
            "latest_month": "YYYY-MM" | None,
            "is_dummy": bool,
            "source": str,
        }
    """
    return _load_turkey_cpi_uncached()
