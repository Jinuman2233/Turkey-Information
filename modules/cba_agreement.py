# =============================================================================
# cba_agreement.py
# -----------------------------------------------------------------------------
# MESS ↔ Türk Metal 단체협약(CBA) 인상률과 물가(인플레이션) 비교 모듈입니다.
#
# 데이터는 2년 협약 주기를 6개월 단위로 나눈 확정 시계열입니다.
# 2년 누적 컬럼은 Option A: 각 완료 사이클의 첫 행에만 값을 두고 나머지는 "".
# 수치는 임의로 바꾸지 않습니다.
# =============================================================================

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CHART_HEIGHT = 240
CHART_MARGIN = dict(t=25, b=10, l=10, r=10)
CYCLE_LABELS = ("2019-2021", "2021-2023", "2023-2025")
CBA_CYCLE_START_ROWS = (0, 4, 8, 12)
CBA_HIGHLIGHT_COLOR = "#e6f2ff"
INFLATION_CUM_COL = "Inflation 2년 누적 (%)"
SALARY_CUM_COL = "Salary increase 2년 누적 (%)"

# Option A: 2년 누적은 사이클 첫 행에만 표기, 나머지는 빈 문자열
CBA_DATA = {
    "Timeline": [
        "2019 Sep ~ 2020 Mar",
        "2020 Mar ~ 2020 Sep",
        "2020 Sep ~ 2021 Mar",
        "2021 Mar ~ 2021 Sep",
        "2021 Sep ~ 2022 Mar",
        "2022 Mar ~ 2022 Sep",
        "2022 Sep ~ 2023 Mar",
        "2023 Mar ~ 2023 Sep",
        "2023 Sep ~ 2024 Mar",
        "2024 Mar ~ 2024 Sep",
        "2024 Sep ~ 2025 Mar",
        "2025 Mar ~ 2025 Sep",
        "2025 Sep ~ 2026 Mar",
    ],
    "Inflation (%)": [
        5.95,
        5.49,
        9.60,
        8.81,
        41.93,
        26.97,
        22.22,
        30.05,
        28.47,
        18.30,
        17.54,
        13.11,
        14.02,
    ],
    "CBA (%)": [
        18.49,
        5.92,
        9.60,
        8.81,
        28.92,
        30.00,
        22.22,
        30.05,
        97.54,
        38.20,
        20.54,
        13.11,
        29.00,
    ],
    INFLATION_CUM_COL: [
        "25.8%",
        "",
        "",
        "",
        "101.8%",
        "",
        "",
        "",
        "57.3%",
        "",
        "",
        "",
        "",
    ],
    SALARY_CUM_COL: [
        "26.3%",
        "",
        "",
        "",
        "106.6%",
        "",
        "",
        "",
        "88.4%",
        "",
        "",
        "",
        "",
    ],
}


def _parse_percent(value) -> float:
    text = str(value).strip().replace("%", "")
    return float(text)


def get_cba_dataframe() -> pd.DataFrame:
    """MESS-Türk Metal 6개월 구간 CBA/물가 확정 테이블."""
    return pd.DataFrame(CBA_DATA)


def _highlight_cba_cycle_starts(row: pd.Series) -> list[str]:
    """2년 협약 주기 첫 행(2019/2021/2023/2025 Sep)을 연한 파란색으로 표시."""
    if row.name in CBA_CYCLE_START_ROWS:
        return [f"background-color: {CBA_HIGHLIGHT_COLOR}"] * len(row)
    return [""] * len(row)


def style_cba_dataframe(df: pd.DataFrame):
    return df.style.apply(_highlight_cba_cycle_starts, axis=1)


def get_cba_cycle_frame(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """완료된 3개 협약 주기(2019-2021, 2021-2023, 2023-2025)의 2년 누적 인상률."""
    source = df if df is not None else get_cba_dataframe()
    rows = source[source[INFLATION_CUM_COL].astype(str).str.strip() != ""].copy()
    rows = rows.reset_index(drop=True)
    if len(rows) != len(CYCLE_LABELS):
        raise ValueError("완료된 CBA 주기 누적 행 수가 3개가 아닙니다.")
    return pd.DataFrame(
        {
            "Cycle": list(CYCLE_LABELS),
            INFLATION_CUM_COL: [_parse_percent(v) for v in rows[INFLATION_CUM_COL]],
            SALARY_CUM_COL: [_parse_percent(v) for v in rows[SALARY_CUM_COL]],
        }
    )


def build_cba_period_figure(df: pd.DataFrame) -> go.Figure:
    """13개 6개월 구간의 Inflation (%) vs CBA (%) 그룹 막대."""
    inflation_vals = df["Inflation (%)"].tolist()
    cba_vals = df["CBA (%)"].tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["Timeline"],
            y=inflation_vals,
            name="Inflation (%)",
            marker_color="#1565C0",
            text=[f"{val}%" for val in inflation_vals],
            textposition="outside",
            textfont=dict(size=10),
            cliponaxis=False,
            hovertemplate="%{x}<br>Inflation: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["Timeline"],
            y=cba_vals,
            name="CBA (%)",
            marker_color="#C8102E",
            text=[f"{val}%" for val in cba_vals],
            textposition="outside",
            textfont=dict(size=10),
            cliponaxis=False,
            hovertemplate="%{x}<br>CBA: %{y:.2f}%<extra></extra>",
        )
    )
    max_val = float(max(max(inflation_vals), max(cba_vals)))
    fig.update_layout(
        barmode="group",
        height=CHART_HEIGHT,
        margin=CHART_MARGIN,
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
        bargap=0.25,
        bargroupgap=0.08,
        yaxis_title="%",
        xaxis_title=None,
    )
    fig.update_xaxes(tickangle=-40, tickfont=dict(size=8), type="category")
    fig.update_yaxes(range=[0, max_val * 1.15], ticksuffix="")
    return fig


def build_cba_cycle_figure(df: pd.DataFrame) -> go.Figure:
    """완료 3주기 2년 누적 Inflation vs Salary increase."""
    cycles = get_cba_cycle_frame(df)
    inflation_vals = cycles[INFLATION_CUM_COL]
    salary_vals = cycles[SALARY_CUM_COL]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=cycles["Cycle"],
            y=inflation_vals,
            name=INFLATION_CUM_COL,
            marker_color="#1565C0",
            text=[f"{v:.1f}%" for v in inflation_vals],
            textposition="outside",
            textfont=dict(size=10),
            cliponaxis=False,
            hovertemplate="%{x}<br>Inflation 2년 누적: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=cycles["Cycle"],
            y=salary_vals,
            name=SALARY_CUM_COL,
            marker_color="#C8102E",
            text=[f"{v:.1f}%" for v in salary_vals],
            textposition="outside",
            textfont=dict(size=10),
            cliponaxis=False,
            hovertemplate="%{x}<br>Salary increase 2년 누적: %{y:.1f}%<extra></extra>",
        )
    )
    y_max = float(max(inflation_vals.max(), salary_vals.max()))
    fig.update_layout(
        barmode="group",
        height=CHART_HEIGHT,
        margin=CHART_MARGIN,
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
        bargap=0.35,
        yaxis_title="%",
        xaxis_title=None,
        yaxis=dict(range=[0, y_max * 1.28]),
    )
    return fig


def render_cba_agreement_section() -> None:
    """최저임금 바로 위에 두는 MESS-Türk Metal CBA 차트+표."""
    df_cba = get_cba_dataframe()
    st.markdown(
        "<div class='section-title'>📑 MESS · Türk Metal 단체협약 (CBA) 인상률</div>",
        unsafe_allow_html=True,
    )
    st.caption("6개월 구간 물가 vs CBA 인상률 · 완료된 2년 주기의 누적 인상률 비교")

    left, right = st.columns([6, 4], gap="small")
    with left:
        st.markdown("**6개월 주기 인상률 추이**")
        st.plotly_chart(
            build_cba_period_figure(df_cba),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        st.markdown("**2개년 주기 누적 인상률 비교**")
        st.plotly_chart(
            build_cba_cycle_figure(df_cba),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.dataframe(
        df_cba.style.apply(_highlight_cba_cycle_starts, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("연한 파란색 행은 새로운 2년 단체협약이 시작되는 구간입니다. 2년 누적 값은 해당 행에만 표기합니다.")
