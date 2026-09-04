# =============================================================================
# macro_industry.py
# -----------------------------------------------------------------------------
# 거시경제(TÜİK CPI·PPI)와 자동차 산업(OSD 연간 생산/수출/내수) 모듈입니다.
#
# 1) CPI(TÜFE) / PPI(Yİ-ÜFE) 전년 동기 대비(YoY) 최근 24개월
# 2) OSD 연간 총 생산·수출·국내판매 (2021~2025 + 당해 YTD)
#
# OSD는 API가 불안정하므로 엑셀 연동 뼈대 + 현실적인 연간 더미를 씁니다.
# 화면에는 expander/tab 없이 항상 바로 렌더링합니다.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta
from plotly.subplots import make_subplots

CACHE_TTL_SECONDS = 60 * 60 * 24
CPI_PPI_MONTHS = 24
OSD_EXCEL_COLUMNS = ("Year", "Production", "Export", "Sales")
OSD_YTD_LABEL = "2026 (YTD)"
OSD_CHART_HEIGHT = 260
OSD_CHART_MARGIN = dict(t=30, b=10, l=10, r=10)

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
# OSD 자동차 연간 생산/수출/내수 (2021~2025 + 당해 YTD)
# 엑셀 컬럼: Year, Production, Export, Sales  → Export_Ratio 는 계산 컬럼
# -----------------------------------------------------------------------------
# 터키 전체 산업 규모에 맞춘 확정 더미 (생산 120~150만, 수출 생산의 65~75%,
# 내수 판매 70~110만). 2026은 연간 누적(YTD)이라 풀이어보다 낮게 둡니다.
OSD_ANNUAL_FALLBACK_ROWS = (
    {"Year": 2021, "Production": 1_276_140, "Export": 937_020, "Sales": 737_350},
    {"Year": 2022, "Production": 1_352_648, "Export": 969_820, "Sales": 783_280},
    {"Year": 2023, "Production": 1_468_403, "Export": 1_014_180, "Sales": 967_340},
    {"Year": 2024, "Production": 1_371_296, "Export": 1_003_450, "Sales": 985_620},
    {"Year": 2025, "Production": 1_425_800, "Export": 1_018_400, "Sales": 1_062_150},
    {"Year": OSD_YTD_LABEL, "Production": 986_420, "Export": 702_180, "Sales": 728_540},
)


def _format_osd_year(value) -> str:
    text = str(value).strip()
    if "YTD" in text.upper():
        return OSD_YTD_LABEL
    try:
        year = int(float(text.replace(",", "")))
        return str(year)
    except (TypeError, ValueError):
        return text


def normalize_osd_annual_df(df: pd.DataFrame) -> pd.DataFrame:
    """엑셀/더미 원본을 Year, Production, Export, Sales, Export_Ratio 로 맞춥니다."""
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in {"year", "연도", "년도"}:
            rename[col] = "Year"
        elif key in {"production", "생산", "생산량", "toplam_uretim", "üretim"}:
            rename[col] = "Production"
        elif key in {"export", "수출", "수출량", "ihracat"}:
            rename[col] = "Export"
        elif key in {"sales", "판매", "판매량", "내수", "국내판매", "pazary"}:
            rename[col] = "Sales"
    out = df.rename(columns=rename).copy()
    missing = [c for c in OSD_EXCEL_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"OSD 연간 데이터에 필요한 컬럼이 없습니다: {missing}")

    out = out[list(OSD_EXCEL_COLUMNS)].copy()
    out["Year"] = out["Year"].map(_format_osd_year)
    for col in ("Production", "Export", "Sales"):
        out[col] = (
            pd.to_numeric(
                out[col].astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False),
                errors="coerce",
            )
            .round()
            .astype("Int64")
        )
    out = out.dropna(subset=["Production", "Export", "Sales"]).reset_index(drop=True)
    if out.empty:
        raise ValueError("OSD 연간 데이터가 비어 있습니다.")
    out["Export_Ratio"] = (out["Export"] / out["Production"] * 100.0).round(1)
    return out


def build_osd_annual_fallback() -> pd.DataFrame:
    """2021~2025 + 2026 YTD 현실적 더미. 엑셀 연동 전 기본 뼈대입니다."""
    return normalize_osd_annual_df(pd.DataFrame(list(OSD_ANNUAL_FALLBACK_ROWS)))


def load_osd_annual_from_excel(file_or_path) -> pd.DataFrame:
    """
    향후 엑셀 업로드 대체용.
    필수 컬럼: Year, Production, Export, Sales
    Export_Ratio 는 없어도 계산합니다.
    """
    from pathlib import Path

    if isinstance(file_or_path, (str, Path)):
        raw = pd.read_excel(file_or_path)
    else:
        from io import BytesIO

        raw = pd.read_excel(BytesIO(file_or_path.read()) if hasattr(file_or_path, "read") else file_or_path)
    return normalize_osd_annual_df(raw)


def build_osd_figure(df: pd.DataFrame) -> go.Figure:
    """생산/수출/판매 그룹 막대 + 수출률 보조축 꺾은선."""
    years = df["Year"].astype(str)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=years,
            y=df["Production"],
            name="생산량",
            marker=dict(color="#C8102E"),
            hovertemplate="%{x}<br>생산: %{y:,.0f}대<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=years,
            y=df["Export"],
            name="수출량",
            marker=dict(color="#1565C0"),
            hovertemplate="%{x}<br>수출: %{y:,.0f}대<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=years,
            y=df["Sales"],
            name="판매량",
            marker=dict(color="#2E7D32"),
            hovertemplate="%{x}<br>판매: %{y:,.0f}대<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=df["Export_Ratio"],
            name="수출률",
            mode="lines+markers",
            line=dict(color="#F9A825", width=2.6),
            marker=dict(size=7, color="#F9A825"),
            hovertemplate="%{x}<br>수출률: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        barmode="group",
        height=OSD_CHART_HEIGHT,
        margin=OSD_CHART_MARGIN,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            xanchor="left",
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        autosize=True,
        bargap=0.28,
        bargroupgap=0.08,
    )
    fig.update_xaxes(title_text=None, type="category")
    fig.update_yaxes(title_text="대수", secondary_y=False, separatethousands=True)
    fig.update_yaxes(title_text="수출률 (%)", secondary_y=True, range=[50, 90], showgrid=False)
    return fig


def _latest_osd_row(df: pd.DataFrame) -> pd.Series:
    ytd = df[df["Year"].astype(str) == OSD_YTD_LABEL]
    if not ytd.empty:
        return ytd.iloc[-1]
    return df.iloc[-1]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_osd_payload() -> dict:
    df = build_osd_annual_fallback()
    latest = _latest_osd_row(df)
    return {
        "df": df,
        "is_dummy": True,
        "source": "dummy:OSD-annual (Excel 연동 뼈대)",
        "latest_year": str(latest["Year"]),
        "latest_production": int(latest["Production"]),
        "latest_export": int(latest["Export"]),
        "latest_sales": int(latest["Sales"]),
        "latest_export_ratio": float(latest["Export_Ratio"]),
    }


def get_osd_auto_trend() -> dict:
    payload = dict(_cached_osd_payload())
    payload["figure"] = build_osd_figure(payload["df"])
    return payload


def render_osd_industry_section(payload: dict | None = None) -> None:
    """하단 우측 컬럼에 expander/tab 없이 OSD 요약+차트를 바로 그립니다."""
    data = payload if payload and payload.get("figure") is not None else get_osd_auto_trend()
    st.markdown(
        "<div class='section-title'>🏭 OSD 자동차 산업 동향 (2021~2026 YTD)</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("총 생산량 (YTD)", f"{data['latest_production']:,}대")
    m2.metric("총 판매량 (YTD)", f"{data['latest_sales']:,}대")
    m3.metric("수출률", f"{data['latest_export_ratio']:.1f}%")
    st.plotly_chart(
        data["figure"],
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )


def get_macro_industry_bundle() -> dict:
    """대시보드 컬럼용 패키지."""
    return {"inflation": get_cpi_ppi_trend(), "auto": get_osd_auto_trend()}
