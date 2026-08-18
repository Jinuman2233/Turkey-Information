# =============================================================================
# energy_data.py
# -----------------------------------------------------------------------------
# 공장 유틸리티 원가 — 산업용 에너지/가스 단가 트렌드 모듈입니다.
#
# 대상:
#   - 산업용 전기 (Electricity, TRY/kWh)
#   - 산업용 천연가스 (Natural Gas, TRY/Sm³)
#   - 질소 (Nitrogen, TRY/Nm³)
#   - 헬륨 (Helium, TRY/Nm³)
#
# 기간: 최근 36개월(3년) 월말(End of Month) 단가
# 환율: yfinance EURTRY=X 의 해당 월 '마지막 거래일 종가'로 TRY → EUR 환산
#
# 외부 공개 API가 없어, pandas DataFrame 기반 Mock 단가를 기본으로 사용합니다.
# 향후 엑셀 업로드 시 load_energy_prices_from_excel() 로 교체하면 됩니다.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

LOOKBACK_MONTHS = 36
CACHE_TTL_SECONDS = 60 * 60 * 24  # 하루
EURTRY_TICKER = "EURTRY=X"

# 화면/테이블 컬럼 (요청 스펙)
TABLE_COLUMNS = [
    "연-월",
    "월말 EUR/TRY 환율",
    "전기(TRY)",
    "전기(EUR)",
    "가스(TRY)",
    "가스(EUR)",
    "질소(TRY)",
    "질소(EUR)",
    "헬륨(TRY)",
    "헬륨(EUR)",
]

# 향후 엑셀 업로드용 내부 키
PRICE_COLUMNS = {
    "electricity_try": "전기(TRY)",
    "gas_try": "가스(TRY)",
    "nitrogen_try": "질소(TRY)",
    "helium_try": "헬륨(TRY)",
}

# 통신 실패 시 월말 EUR/TRY mock (대략적 역사 수준)
FALLBACK_EOM_EURTRY: dict[str, float] = {
    "2023-09": 28.85,
    "2023-10": 28.95,
    "2023-11": 31.40,
    "2023-12": 32.55,
    "2024-01": 33.15,
    "2024-02": 33.85,
    "2024-03": 34.95,
    "2024-04": 34.70,
    "2024-05": 35.05,
    "2024-06": 35.45,
    "2024-07": 36.05,
    "2024-08": 37.55,
    "2024-09": 38.15,
    "2024-10": 37.45,
    "2024-11": 36.85,
    "2024-12": 36.95,
    "2025-01": 37.55,
    "2025-02": 38.15,
    "2025-03": 38.85,
    "2025-04": 39.45,
    "2025-05": 40.05,
    "2025-06": 40.65,
    "2025-07": 41.25,
    "2025-08": 41.85,
    "2025-09": 42.45,
    "2025-10": 42.95,
    "2025-11": 43.45,
    "2025-12": 43.95,
    "2026-01": 44.55,
    "2026-02": 45.05,
    "2026-03": 45.55,
    "2026-04": 46.05,
    "2026-05": 46.55,
    "2026-06": 47.05,
    "2026-07": 47.55,
    "2026-08": 48.05,
}


def _month_ends(n_months: int = LOOKBACK_MONTHS, as_of: datetime | None = None) -> pd.DatetimeIndex:
    """최근 n개월의 월말(캘린더) Timestamp 인덱스."""
    as_of = as_of or datetime.now()
    end = pd.Timestamp(as_of).to_period("M").to_timestamp("M")
    start = (end.to_period("M") - (n_months - 1)).to_timestamp("M")
    try:
        return pd.date_range(start=start, end=end, freq="ME")
    except ValueError:
        return pd.date_range(start=start, end=end, freq="M")


def build_mock_energy_prices(n_months: int = LOOKBACK_MONTHS, as_of: datetime | None = None) -> pd.DataFrame:
    """
    현실적인 36개월 Mock 단가(TRY) DataFrame을 생성합니다.

    - 전기/가스: 완만한 상승 추세 + 계절성
    - 질소: 중저가 밴드 내 변동
    - 헬륨: 고가 밴드 내 공급 이슈성 출렁임
    """
    months = _month_ends(n_months=n_months, as_of=as_of)
    n = len(months)
    t = np.arange(n, dtype=float)

    # 재현 가능한 더미 (엑셀 대체 전까지 화면이 흔들리지 않도록)
    rng = np.random.default_rng(20260818)

    # 산업용 전기 ~ 2.4 → 5.1 TRY/kWh (상승)
    electricity = 2.40 + 0.055 * t + 0.18 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 0.04, n)
    electricity = np.clip(electricity, 2.1, 6.5)

    # 산업용 가스 ~ 8.5 → 18.5 TRY/Sm³ (상승, 겨울 피크)
    winter = 0.9 * np.maximum(0, np.cos(2 * np.pi * (t + 2) / 12))
    gas = 8.50 + 0.22 * t + winter + rng.normal(0, 0.12, n)
    gas = np.clip(gas, 7.5, 22.0)

    # 질소 ~ 9~14 TRY/Nm³ 밴드
    nitrogen = 11.2 + 1.6 * np.sin(2 * np.pi * t / 9) + 0.35 * np.sin(2 * np.pi * t / 4) + rng.normal(0, 0.15, n)
    nitrogen = np.clip(nitrogen, 8.5, 14.5)

    # 헬륨 ~ 950~1450 TRY/Nm³, 간헐적 급등
    helium = 1080 + 90 * np.sin(2 * np.pi * t / 14) + rng.normal(0, 18, n)
    spikes = np.zeros(n)
    spike_idx = [7, 18, 29]
    for i in spike_idx:
        if 0 <= i < n:
            spikes[i] = 180
            if i + 1 < n:
                spikes[i + 1] = 90
    helium = np.clip(helium + spikes, 920, 1550)

    return pd.DataFrame(
        {
            "month_end": months,
            "electricity_try": np.round(electricity, 4),
            "gas_try": np.round(gas, 4),
            "nitrogen_try": np.round(nitrogen, 4),
            "helium_try": np.round(helium, 4),
        }
    )


def load_energy_prices_from_excel(file_or_path) -> pd.DataFrame:
    """
    향후 엑셀 업로드 대체용.
    필수 컬럼: month_end(또는 연-월), electricity_try, gas_try, nitrogen_try, helium_try
    """
    if isinstance(file_or_path, (str, Path)):
        raw = pd.read_excel(file_or_path)
    else:
        raw = pd.read_excel(BytesIO(file_or_path.read()) if hasattr(file_or_path, "read") else file_or_path)

    rename = {}
    for col in raw.columns:
        key = str(col).strip().lower()
        if key in {"month", "month_end", "연-월", "date", "날짜"}:
            rename[col] = "month_end"
        elif "electric" in key or key in {"전기", "전기(try)"}:
            rename[col] = "electricity_try"
        elif "gas" in key or key in {"가스", "가스(try)"}:
            rename[col] = "gas_try"
        elif "nitrogen" in key or "질소" in key:
            rename[col] = "nitrogen_try"
        elif "helium" in key or "헬륨" in key:
            rename[col] = "helium_try"
    df = raw.rename(columns=rename).copy()
    required = ["month_end", "electricity_try", "gas_try", "nitrogen_try", "helium_try"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"엑셀에 필요한 컬럼이 없습니다: {missing}")

    df["month_end"] = pd.to_datetime(df["month_end"]).dt.to_period("M").dt.to_timestamp("M")
    return df[required].sort_values("month_end").reset_index(drop=True)


def _fallback_eurtry_series(months: pd.DatetimeIndex) -> pd.Series:
    """월말 mock EUR/TRY. 없는 달은 선형 보간/전후 채움."""
    values = []
    last = 32.0
    for ts in months:
        key = ts.strftime("%Y-%m")
        if key in FALLBACK_EOM_EURTRY:
            last = FALLBACK_EOM_EURTRY[key]
        else:
            last = round(last * 1.012, 4)
        values.append(last)
    return pd.Series(values, index=months, name="eur_try_eom")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_eurtry_month_end_close(start: str, end: str) -> pd.Series | None:
    """
    yfinance EURTRY=X 일봉에서 각 월의 마지막 거래일 종가를 추출합니다.
    실패 시 None.
    """
    try:
        raw = yf.download(
            EURTRY_TICKER,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if raw is None or raw.empty:
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].copy()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
        else:
            close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]

        close = pd.to_numeric(close, errors="coerce").dropna()
        if close.empty:
            return None

        month_end = close.groupby(close.index.to_period("M")).last()
        month_end.index = month_end.index.to_timestamp("M")
        month_end.name = "eur_try_eom"
        return month_end.astype(float)
    except Exception:
        return None


def _attach_eur_prices(prices: pd.DataFrame, eur_try: pd.Series) -> pd.DataFrame:
    """TRY 단가에 월말 EUR/TRY를 붙여 EUR 단가를 계산합니다."""
    df = prices.copy()
    df["month_end"] = pd.to_datetime(df["month_end"]).dt.to_period("M").dt.to_timestamp("M")
    fx = pd.to_numeric(eur_try, errors="coerce").copy()
    fx.index = pd.to_datetime(fx.index).to_period("M").to_timestamp("M")
    fx = fx.groupby(fx.index).last()

    fallback = _fallback_eurtry_series(pd.DatetimeIndex(df["month_end"]))
    combined = fallback.copy()
    combined.update(fx.reindex(combined.index))
    combined = combined.ffill().bfill()

    df["eur_try_eom"] = df["month_end"].map(combined.to_dict()).astype(float)
    df["eur_try_eom"] = df["eur_try_eom"].ffill().bfill()

    for try_col, eur_col in (
        ("electricity_try", "electricity_eur"),
        ("gas_try", "gas_eur"),
        ("nitrogen_try", "nitrogen_eur"),
        ("helium_try", "helium_eur"),
    ):
        df[eur_col] = df[try_col] / df["eur_try_eom"]
    return df


def _format_display_table(df: pd.DataFrame) -> pd.DataFrame:
    """요청 컬럼 구성 + 소수점 2자리 표시용 테이블."""
    display = pd.DataFrame(
        {
            "연-월": pd.to_datetime(df["month_end"]).dt.strftime("%Y-%m"),
            "월말 EUR/TRY 환율": df["eur_try_eom"].astype(float).round(2),
            "전기(TRY)": df["electricity_try"].astype(float).round(2),
            "전기(EUR)": df["electricity_eur"].astype(float).round(2),
            "가스(TRY)": df["gas_try"].astype(float).round(2),
            "가스(EUR)": df["gas_eur"].astype(float).round(2),
            "질소(TRY)": df["nitrogen_try"].astype(float).round(2),
            "질소(EUR)": df["nitrogen_eur"].astype(float).round(2),
            "헬륨(TRY)": df["helium_try"].astype(float).round(2),
            "헬륨(EUR)": df["helium_eur"].astype(float).round(2),
        }
    )
    return display[TABLE_COLUMNS]


def build_energy_eur_trend_figure(df: pd.DataFrame) -> go.Figure:
    """
    4개 항목의 EUR 단가 꺾은선 차트 (테이블 위에 표시).
    헬륨 단가가 한 자릿수 이상 커서, 전기/가스/질소는 주축, 헬륨은 보조축입니다.
    """
    from plotly.subplots import make_subplots

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    x = pd.to_datetime(df["month_end"])
    primary = [
        ("electricity_eur", "전기 (EUR/kWh)", "#C8102E"),
        ("gas_eur", "가스 (EUR/Sm³)", "#1565C0"),
        ("nitrogen_eur", "질소 (EUR/Nm³)", "#2E7D32"),
    ]
    for col, name, color in primary:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df[col],
                name=name,
                mode="lines+markers",
                line=dict(color=color, width=2.4),
                marker=dict(size=6, color=color),
                hovertemplate="%{x|%Y-%m}<br>%{y:.3f} EUR<extra>" + name + "</extra>",
            ),
            secondary_y=False,
        )

    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["helium_eur"],
            name="헬륨 (EUR/Nm³)",
            mode="lines+markers",
            line=dict(color="#6A1B9A", width=2.4, dash="dot"),
            marker=dict(size=6, color="#6A1B9A"),
            hovertemplate="%{x|%Y-%m}<br>%{y:.2f} EUR<extra>헬륨 (EUR/Nm³)</extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        margin=dict(t=30, b=10, l=10, r=10),
        height=260,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        autosize=True,
    )
    fig.update_xaxes(title_text="연-월", tickformat="%Y-%m", dtick="M3")
    fig.update_yaxes(title_text="전기·가스·질소 (EUR)", secondary_y=False)
    fig.update_yaxes(title_text="헬륨 (EUR)", secondary_y=True, showgrid=False)
    return fig


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="산업용 에너지/가스 단가와 월말 EUR/TRY를 준비하는 중입니다...")
def get_energy_price_bundle(n_months: int = LOOKBACK_MONTHS) -> dict:
    """
    대시보드용 패키지.

    Returns
    -------
    dict
        dataframe, display_table, figure, is_fx_fallback, source
    """
    prices = build_mock_energy_prices(n_months=n_months)
    start = (pd.Timestamp(prices["month_end"].min()) - pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(prices["month_end"].max()) + pd.offsets.Day(3)).strftime("%Y-%m-%d")

    live_fx = fetch_eurtry_month_end_close(start, end)
    mock_fx = _fallback_eurtry_series(pd.DatetimeIndex(prices["month_end"]))
    if live_fx is None or live_fx.empty:
        eur_try = mock_fx
        is_fx_fallback = True
        fx_note = "fallback:mock_eom_eurtry"
    else:
        live_aligned = live_fx.copy()
        live_aligned.index = pd.to_datetime(live_aligned.index).to_period("M").to_timestamp("M")
        live_aligned = live_aligned.groupby(live_aligned.index).last()
        eur_try = mock_fx.copy()
        eur_try.update(live_aligned.reindex(eur_try.index).dropna())
        missing = int(eur_try.index.difference(live_aligned.dropna().index).size)
        is_fx_fallback = missing > 0
        fx_note = "mixed:yfinance+fallback" if is_fx_fallback else "yfinance:EURTRY=X 월말 종가"

    merged = _attach_eur_prices(prices, eur_try)
    display = _format_display_table(merged)
    figure = build_energy_eur_trend_figure(merged)
    return {
        "dataframe": merged,
        "display_table": display,
        "figure": figure,
        "is_fx_fallback": bool(is_fx_fallback),
        "source": (
            f"Mock 단가(향후 엑셀 대체) · {n_months}개월 월말 · "
            f"EUR 환산({fx_note})"
        ),
    }
