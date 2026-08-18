# =============================================================================
# macro_industry.py
# -----------------------------------------------------------------------------
# 거시경제(TÜİK CPI·PPI)와 자동차 산업(OSD 생산/수출) 요약 모듈입니다.
#
# 1) CPI(TÜFE) / PPI(Yİ-ÜFE) 전년 동기 대비(YoY) 최근 24개월
# 2) OSD 월간 총 생산·수출 대수 최근 12개월
#
# 외부 수집이 실패해도 현실적인 더미로 차트가 비지 않도록 방어합니다.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta
from plotly.subplots import make_subplots

CACHE_TTL_SECONDS = 60 * 60 * 24
CPI_PPI_MONTHS = 24
OSD_MONTHS = 12

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TurkeyBusinessDashboard/1.0; "
        "+https://github.com/Jinuman2233/Turkey-Information)"
    )
}

TCMB_PPI_URLS = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Uretici+Fiyatlari",
    "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Statistics/Inflation+Data/Producer+Prices",
)

OSD_URLS = (
    "https://www.osd.org.tr/en/statistics",
    "https://www.osd.org.tr/istatistikler",
)

FRED_PPI_TICKERS = (
    "TURPROPRICISMEI",  # Turkey Producer Prices
    "TURPPI",
)

# -----------------------------------------------------------------------------
# 현실적인 24개월 CPI/PPI YoY 더미 (물가 고점 후 둔화 → 2026 재가속 일부 반영)
# PPI(생산자)가 CPI보다 먼저 움직이며 갭이 보이는 구조
# -----------------------------------------------------------------------------
CPI_YOY_FALLBACK: dict[str, float] = {
    "2024-09": 49.38,
    "2024-10": 48.58,
    "2024-11": 47.09,
    "2024-12": 44.38,
    "2025-01": 42.12,
    "2025-02": 39.05,
    "2025-03": 38.10,
    "2025-04": 37.86,
    "2025-05": 35.41,
    "2025-06": 35.05,
    "2025-07": 33.52,
    "2025-08": 32.95,
    "2025-09": 33.29,
    "2025-10": 32.87,
    "2025-11": 31.07,
    "2025-12": 30.89,
    "2026-01": 30.65,
    "2026-02": 31.53,
    "2026-03": 30.87,
    "2026-04": 32.37,
    "2026-05": 32.61,
    "2026-06": 32.11,
    "2026-07": 31.85,
    "2026-08": 31.40,
}

PPI_YOY_FALLBACK: dict[str, float] = {
    "2024-09": 33.09,
    "2024-10": 32.24,
    "2024-11": 29.47,
    "2024-12": 28.52,
    "2025-01": 27.20,
    "2025-02": 25.21,
    "2025-03": 23.50,
    "2025-04": 22.50,
    "2025-05": 23.13,
    "2025-06": 24.45,
    "2025-07": 24.20,
    "2025-08": 25.21,
    "2025-09": 26.10,
    "2025-10": 27.00,
    "2025-11": 26.40,
    "2025-12": 25.60,
    "2026-01": 24.80,
    "2026-02": 25.90,
    "2026-03": 25.40,
    "2026-04": 27.10,
    "2026-05": 27.80,
    "2026-06": 27.20,
    "2026-07": 26.90,
    "2026-08": 26.40,
}


def _month_index(n_months: int, as_of: datetime | None = None) -> pd.DatetimeIndex:
    as_of = as_of or datetime.now()
    end = pd.Timestamp(as_of).to_period("M").to_timestamp("M")
    start = (end.to_period("M") - (n_months - 1)).to_timestamp("M")
    try:
        return pd.date_range(start=start, end=end, freq="ME")
    except ValueError:
        return pd.date_range(start=start, end=end, freq="M")


def _yoy_dict_to_frame(values: dict[str, float], col: str, n_months: int = CPI_PPI_MONTHS) -> pd.DataFrame:
    months = _month_index(n_months)
    rows = []
    last = None
    for ts in months:
        key = ts.strftime("%Y-%m")
        if key in values:
            last = float(values[key])
        rows.append({"날짜": ts, "연월": key, col: last})
    df = pd.DataFrame(rows)
    df[col] = df[col].ffill().bfill()
    return df


def build_cpi_ppi_fallback(n_months: int = CPI_PPI_MONTHS) -> pd.DataFrame:
    """CPI·PPI YoY 24개월 더미 (최근 둔화 후 소폭 반등)."""
    cpi = _yoy_dict_to_frame(CPI_YOY_FALLBACK, "CPI_YoY", n_months)
    ppi = _yoy_dict_to_frame(PPI_YOY_FALLBACK, "PPI_YoY", n_months)
    return cpi.merge(ppi[["날짜", "PPI_YoY"]], on="날짜", how="left")


def _live_cpi_yoy_frame(n_months: int = CPI_PPI_MONTHS) -> pd.DataFrame | None:
    """기존 TÜİK CPI 모듈에서 YoY를 가져옵니다."""
    try:
        from modules.cpi_data import get_turkey_cpi_data

        payload = get_turkey_cpi_data()
        df = payload.get("df")
        if df is None or df.empty or "YoY(%)" not in df.columns:
            return None
        out = df[["날짜", "YoY(%)"]].copy()
        out = out.rename(columns={"YoY(%)": "CPI_YoY"})
        out["날짜"] = pd.to_datetime(out["날짜"]).dt.to_period("M").dt.to_timestamp("M")
        out = out.sort_values("날짜").tail(n_months).reset_index(drop=True)
        if len(out) < 12:
            return None
        return out
    except Exception:
        return None


def _fetch_tcmb_ppi_yoy() -> pd.DataFrame:
    """TCMB 재공표 Yİ-ÜFE(생산자물가) 표에서 YoY를 파싱합니다."""
    last_error = None
    for url in TCMB_PPI_URLS:
        try:
            response = requests.get(url, timeout=20, headers=HTTP_HEADERS)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError("PPI HTML 표 없음")
            raw = max(tables, key=lambda t: len(t)).copy()
            raw.columns = [str(c).strip() for c in raw.columns]
            month_col = raw.columns[0]

            # 첫 행이 'ÜFE / Yİ-ÜFE' 서브헤더인 경우 컬럼을 재지정
            first = [str(v).upper() for v in raw.iloc[0].tolist()]
            if any(("Yİ-ÜFE" in x) or ("YI-UFE" in x) or (x.strip() in {"ÜFE", "UFE"}) for x in first):
                raw.columns = [f"{col}|{tag}" for col, tag in zip(raw.columns, first)]
                month_col = raw.columns[0]
                raw = raw.iloc[1:].copy()

            yoy_col = None
            for col in raw.columns:
                name = str(col).upper().replace("I", "İ")
                if "YILLIK" in name or "YEAR" in name:
                    if "Yİ-ÜFE" in name or "YI-UFE" in name or "YİÜFE" in name.replace("-", ""):
                        yoy_col = col
                        break
                    if yoy_col is None:
                        yoy_col = col
            if yoy_col is None:
                # 숫자 컬럼 중 결측이 가장 적은 것
                numeric_ok = []
                for col in raw.columns[1:]:
                    parsed = pd.to_numeric(
                        raw[col].astype(str).str.replace(",", ".", regex=False),
                        errors="coerce",
                    )
                    numeric_ok.append((parsed.notna().sum(), col))
                yoy_col = max(numeric_ok)[1] if numeric_ok else raw.columns[1]

            rows = []
            for _, row in raw.iterrows():
                month_raw = str(row[month_col]).strip()
                month = pd.to_datetime(month_raw, errors="coerce")
                if pd.isna(month):
                    for fmt in ("%m-%Y", "%Y-%m", "%m.%Y", "%Y.%m"):
                        try:
                            month = datetime.strptime(month_raw, fmt)
                            break
                        except ValueError:
                            continue
                try:
                    yoy = float(str(row[yoy_col]).replace(",", ".").replace("%", ""))
                except (TypeError, ValueError):
                    continue
                if pd.isna(month) or pd.isna(yoy):
                    continue
                ts = pd.Timestamp(month).to_period("M").to_timestamp("M")
                rows.append({"날짜": ts, "PPI_YoY": yoy})
            if len(rows) < 12:
                raise RuntimeError("PPI 행 부족")
            frame = pd.DataFrame(rows).drop_duplicates("날짜").sort_values("날짜")
            frame = frame.dropna(subset=["PPI_YoY"])
            if frame.empty:
                raise RuntimeError("PPI YoY가 모두 비어 있습니다.")
            return frame.reset_index(drop=True)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"TCMB PPI 수집 실패: {last_error}")


def _fetch_fred_ppi_yoy() -> pd.DataFrame:
    """FRED 터키 생산자물가 지수로 YoY(%)를 계산합니다."""
    from pandas_datareader import data as web

    end = datetime.today()
    start = end - relativedelta(months=48)
    last_error = None
    for ticker in FRED_PPI_TICKERS:
        try:
            raw = web.DataReader(ticker, "fred", start, end)
            if raw is None or raw.empty:
                continue
            series = raw.iloc[:, 0].dropna()
            yoy = series.pct_change(12) * 100.0
            frame = yoy.dropna().to_frame("PPI_YoY")
            frame["날짜"] = pd.to_datetime(frame.index).to_period("M").to_timestamp("M")
            return frame[["날짜", "PPI_YoY"]].reset_index(drop=True)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"FRED PPI 수집 실패: {last_error}")


def _merge_cpi_ppi(cpi: pd.DataFrame, ppi: pd.DataFrame, n_months: int) -> pd.DataFrame:
    months = _month_index(n_months)
    base = pd.DataFrame({"날짜": months})
    cpi = cpi.copy()
    ppi = ppi.copy()
    cpi["날짜"] = pd.to_datetime(cpi["날짜"]).dt.to_period("M").dt.to_timestamp("M")
    ppi["날짜"] = pd.to_datetime(ppi["날짜"]).dt.to_period("M").dt.to_timestamp("M")
    merged = base.merge(cpi[["날짜", "CPI_YoY"]], on="날짜", how="left")
    merged = merged.merge(ppi[["날짜", "PPI_YoY"]], on="날짜", how="left")
    merged["CPI_YoY"] = merged["CPI_YoY"].ffill().bfill()
    merged["PPI_YoY"] = merged["PPI_YoY"].ffill().bfill()
    # 최근 월 PPI가 아직 없으면 더미로 메움 (차트 공백 방지)
    dummy = build_cpi_ppi_fallback(n_months)
    if merged["PPI_YoY"].isna().any():
        dummy_ppi = dummy.set_index("날짜")["PPI_YoY"]
        merged["PPI_YoY"] = merged["PPI_YoY"].fillna(merged["날짜"].map(dummy_ppi))
        merged["PPI_YoY"] = merged["PPI_YoY"].ffill().bfill()
    if merged["CPI_YoY"].isna().any():
        dummy_cpi = dummy.set_index("날짜")["CPI_YoY"]
        merged["CPI_YoY"] = merged["CPI_YoY"].fillna(merged["날짜"].map(dummy_cpi))
        merged["CPI_YoY"] = merged["CPI_YoY"].ffill().bfill()
    merged["연월"] = merged["날짜"].dt.strftime("%Y-%m")
    merged["갭(CPI-PPI)"] = merged["CPI_YoY"] - merged["PPI_YoY"]
    return merged.tail(n_months).reset_index(drop=True)


def build_cpi_ppi_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["날짜"],
            y=df["CPI_YoY"],
            name="CPI / TÜFE YoY",
            mode="lines+markers",
            line=dict(color="#C8102E", width=2.6),
            marker=dict(size=5),
            hovertemplate="%{x|%Y-%m}<br>CPI YoY: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["날짜"],
            y=df["PPI_YoY"],
            name="PPI / Yİ-ÜFE YoY",
            mode="lines+markers",
            line=dict(color="#1565C0", width=2.6),
            marker=dict(size=5),
            hovertemplate="%{x|%Y-%m}<br>PPI YoY: %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(t=18, b=6, l=8, r=8),
        height=180,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"),
        hovermode="x unified",
        autosize=True,
    )
    fig.update_xaxes(title_text=None, tickformat="%Y-%m", dtick="M3")
    fig.update_yaxes(title_text="YoY (%)")
    return fig


def _assemble_cpi_ppi(n_months: int = CPI_PPI_MONTHS) -> dict:
    """CPI·PPI YoY 24개월 시계열(피규어 제외, 캐시 가능)."""
    is_dummy = False
    source_bits = []
    cpi_live = _live_cpi_yoy_frame(n_months)
    ppi_live = None
    try:
        ppi_live = _fetch_tcmb_ppi_yoy()
        source_bits.append("PPI:TCMB")
    except Exception:
        try:
            ppi_live = _fetch_fred_ppi_yoy()
            source_bits.append("PPI:FRED")
        except Exception:
            ppi_live = None

    fallback = build_cpi_ppi_fallback(n_months)
    if cpi_live is not None:
        source_bits.append("CPI:TÜİK")
        cpi_part = cpi_live
    else:
        is_dummy = True
        source_bits.append("CPI:dummy")
        cpi_part = fallback[["날짜", "CPI_YoY"]]

    if ppi_live is not None and not ppi_live.empty:
        ppi_part = ppi_live
    else:
        is_dummy = True
        source_bits.append("PPI:dummy")
        ppi_part = fallback[["날짜", "PPI_YoY"]]

    df = _merge_cpi_ppi(cpi_part, ppi_part, n_months)
    latest = df.iloc[-1]
    return {
        "df": df,
        "is_dummy": is_dummy,
        "source": " · ".join(source_bits),
        "latest_cpi": float(latest["CPI_YoY"]),
        "latest_ppi": float(latest["PPI_YoY"]),
        "latest_gap": float(latest["갭(CPI-PPI)"]),
        "latest_month": str(latest["연월"]),
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_cpi_ppi_payload(n_months: int = CPI_PPI_MONTHS) -> dict:
    try:
        return _assemble_cpi_ppi(n_months)
    except Exception:
        df = build_cpi_ppi_fallback(n_months)
        latest = df.iloc[-1]
        return {
            "df": df,
            "is_dummy": True,
            "source": "CPI:dummy · PPI:dummy",
            "latest_cpi": float(latest["CPI_YoY"]),
            "latest_ppi": float(latest["PPI_YoY"]),
            "latest_gap": float(latest["갭(CPI-PPI)"]),
            "latest_month": str(latest["연월"]),
        }


def get_cpi_ppi_trend(n_months: int = CPI_PPI_MONTHS) -> dict:
    payload = dict(_cached_cpi_ppi_payload(n_months))
    payload["figure"] = build_cpi_ppi_figure(payload["df"])
    return payload


# -----------------------------------------------------------------------------
# OSD 자동차 생산/수출 (월 10~15만 대 수준 더미 + 선택적 크롤)
# -----------------------------------------------------------------------------
def build_osd_fallback(n_months: int = OSD_MONTHS, as_of: datetime | None = None) -> pd.DataFrame:
    """
    터키 OSD 월간 생산 10만~15만 대, 수출은 생산의 약 70~80% 더미.
    YoY 계산을 위해 내부적으로 24개월을 만든 뒤 최근 n_months만 반환합니다.
    """
    months = _month_index(n_months + 12, as_of=as_of)
    rng = np.random.default_rng(20260818)
    n = len(months)
    t = np.arange(n, dtype=float)
    seasonal = 8000 * np.sin(2 * np.pi * (t + 2) / 12)
    production = 118_000 + 900 * t + seasonal + rng.normal(0, 2500, n)
    production = np.clip(production, 100_000, 150_000)
    export_ratio = 0.74 + 0.04 * np.sin(2 * np.pi * t / 10)
    export = np.clip(production * export_ratio + rng.normal(0, 1500, n), 75_000, 140_000)

    df = pd.DataFrame(
        {
            "날짜": months,
            "생산량": np.round(production).astype(int),
            "수출량": np.round(export).astype(int),
        }
    )
    df["연월"] = df["날짜"].dt.strftime("%Y-%m")
    df["생산_YoY"] = df["생산량"].pct_change(12) * 100.0
    df["수출_YoY"] = df["수출량"].pct_change(12) * 100.0
    return df.tail(n_months).reset_index(drop=True)


def _fetch_osd_monthly() -> pd.DataFrame:
    """OSD 통계 페이지에서 월간 생산/수출 표를 시도합니다. 실패하면 예외."""
    last_error = None
    for url in OSD_URLS:
        try:
            response = requests.get(url, timeout=15, headers=HTTP_HEADERS)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError("OSD 표 없음")
            raw = max(tables, key=lambda t: len(t)).copy()
            raw.columns = [str(c).strip() for c in raw.columns]
            prod_col = None
            exp_col = None
            month_col = raw.columns[0]
            for col in raw.columns:
                name = str(col).lower()
                if prod_col is None and ("üretim" in name or "production" in name or "생산" in name):
                    prod_col = col
                if exp_col is None and ("ihracat" in name or "export" in name or "수출" in name):
                    exp_col = col
            if prod_col is None or exp_col is None:
                raise RuntimeError(f"OSD 컬럼 미인식: {list(raw.columns)}")
            rows = []
            for _, row in raw.iterrows():
                try:
                    month = pd.to_datetime(str(row[month_col]), errors="coerce")
                    prod = int(float(str(row[prod_col]).replace(".", "").replace(",", "")))
                    exp = int(float(str(row[exp_col]).replace(".", "").replace(",", "")))
                except (TypeError, ValueError):
                    continue
                if pd.isna(month) or prod < 10_000:
                    continue
                ts = pd.Timestamp(month).to_period("M").to_timestamp("M")
                rows.append({"날짜": ts, "생산량": prod, "수출량": exp})
            if len(rows) < 6:
                raise RuntimeError("OSD 행 부족")
            df = pd.DataFrame(rows).drop_duplicates("날짜").sort_values("날짜")
            df["연월"] = df["날짜"].dt.strftime("%Y-%m")
            df["생산_YoY"] = df["생산량"].pct_change(12) * 100.0
            df["수출_YoY"] = df["수출량"].pct_change(12) * 100.0
            return df.tail(OSD_MONTHS).reset_index(drop=True)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"OSD 수집 실패: {last_error}")


def build_osd_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    fig.add_trace(
        go.Bar(
            x=df["날짜"],
            y=df["생산량"],
            name="총 생산량",
            marker=dict(color="rgba(200, 16, 46, 0.45)"),
            hovertemplate="%{x|%Y-%m}<br>생산: %{y:,.0f}대<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["날짜"],
            y=df["수출량"],
            name="수출량",
            mode="lines+markers",
            line=dict(color="#1565C0", width=2.6),
            marker=dict(size=6),
            hovertemplate="%{x|%Y-%m}<br>수출: %{y:,.0f}대<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(t=18, b=6, l=8, r=8),
        height=180,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"),
        hovermode="x unified",
        barmode="overlay",
        autosize=True,
    )
    fig.update_xaxes(title_text=None, tickformat="%Y-%m", dtick="M1")
    fig.update_yaxes(title_text="대수")
    return fig


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_osd_payload(n_months: int = OSD_MONTHS) -> dict:
    try:
        df = _fetch_osd_monthly()
        is_dummy = False
        source = "OSD"
    except Exception:
        df = build_osd_fallback(n_months=n_months)
        is_dummy = True
        source = "dummy:OSD-scale"

    latest = df.iloc[-1]
    prod_yoy = latest["생산_YoY"]
    exp_yoy = latest["수출_YoY"]
    if pd.isna(prod_yoy):
        prod_yoy = 0.0
    if pd.isna(exp_yoy):
        exp_yoy = 0.0

    return {
        "df": df,
        "is_dummy": is_dummy,
        "source": source,
        "latest_month": str(latest["연월"]),
        "latest_production": int(latest["생산량"]),
        "latest_export": int(latest["수출량"]),
        "production_yoy": float(prod_yoy),
        "export_yoy": float(exp_yoy),
    }


def get_osd_auto_trend(n_months: int = OSD_MONTHS) -> dict:
    payload = dict(_cached_osd_payload(n_months))
    payload["figure"] = build_osd_figure(payload["df"])
    return payload


def get_macro_industry_bundle() -> dict:
    """대시보드 탭/컬럼용 패키지."""
    return {"inflation": get_cpi_ppi_trend(), "auto": get_osd_auto_trend()}
