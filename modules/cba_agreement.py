# =============================================================================
# cba_agreement.py
# -----------------------------------------------------------------------------
# MESS ↔ Türk Metal 단체협약(CBA) 인상률과 물가(인플레이션) 비교 모듈입니다.
#
# 데이터는 2년 협약 주기를 6개월 단위로 나눈 확정 시계열입니다.
# YOY 컬럼은 Option A: 각 완료 사이클의 첫 행에만 값을 두고 나머지는 "".
# 수치는 임의로 바꾸지 않습니다.
# =============================================================================

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CHART_HEIGHT = 240
CHART_MARGIN = dict(t=25, b=10, l=10, r=10)
YOY_CYCLE_LABELS = ("2019-2021", "2021-2023", "2023-2025")

# Option A: 2년 주기 YOY는 사이클 첫 행에만 표기, 나머지는 빈 문자열
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
    "Inflation YOY (%)": [
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
    "Salary increase YOY (%)": [
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


def _parse_yoy_percent(value) -> float:
    text = str(value).strip().replace("%", "")
    return float(text)


def get_cba_dataframe() -> pd.DataFrame:
    """MESS-Türk Metal 6개월 구간 CBA/물가 확정 테이블."""
    return pd.DataFrame(CBA_DATA)


def get_cba_yoy_cycle_frame(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """완료된 3개 협약 주기(2019-2021, 2021-2023, 2023-2025)의 누적 YOY."""
    source = df if df is not None else get_cba_dataframe()
    rows = source[source["Inflation YOY (%)"].astype(str).str.strip() != ""].copy()
    rows = rows.reset_index(drop=True)
    if len(rows) != len(YOY_CYCLE_LABELS):
        raise ValueError("완료된 CBA 주기 YOY 행 수가 3개가 아닙니다.")
    return pd.DataFrame(
        {
            "Cycle": list(YOY_CYCLE_LABELS),
            "Inflation YOY": [_parse_yoy_percent(v) for v in rows["Inflation YOY (%)"]],
            "Salary increase YOY": [
                _parse_yoy_percent(v) for v in rows["Salary increase YOY (%)"]
            ],
        }
    )


def build_cba_period_figure(df: pd.DataFrame) -> go.Figure:
    """13개 6개월 구간의 Inflation (%) vs CBA (%) 그룹 막대."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["Timeline"],
            y=df["Inflation (%)"],
            name="Inflation (%)",
            marker_color="#1565C0",
            hovertemplate="%{x}<br>Inflation: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["Timeline"],
            y=df["CBA (%)"],
            name="CBA (%)",
            marker_color="#C8102E",
            hovertemplate="%{x}<br>CBA: %{y:.2f}%<extra></extra>",
        )
    )
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
    fig.update_yaxes(ticksuffix="")
    return fig


def build_cba_yoy_figure(df: pd.DataFrame) -> go.Figure:
    """완료 3주기 누적 Inflation YOY vs Salary increase YOY."""
    yoy = get_cba_yoy_cycle_frame(df)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=yoy["Cycle"],
            y=yoy["Inflation YOY"],
            name="Inflation YOY",
            marker_color="#1565C0",
            text=[f"{v:.1f}%" for v in yoy["Inflation YOY"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>Inflation YOY: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=yoy["Cycle"],
            y=yoy["Salary increase YOY"],
            name="Salary increase YOY",
            marker_color="#C8102E",
            text=[f"{v:.1f}%" for v in yoy["Salary increase YOY"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>Salary increase YOY: %{y:.1f}%<extra></extra>",
        )
    )
    y_max = float(max(yoy["Inflation YOY"].max(), yoy["Salary increase YOY"].max()))
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
    st.caption("6개월 구간 물가 vs CBA 인상률 · 완료된 2년 주기의 누적 YOY 비교 (Option A)")

    left, right = st.columns([6, 4], gap="small")
    with left:
        st.markdown("**6개월 주기 인상률 추이**")
        st.plotly_chart(
            build_cba_period_figure(df_cba),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        st.markdown("**2개년 주기 누적 YOY 비교**")
        st.plotly_chart(
            build_cba_yoy_figure(df_cba),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.dataframe(df_cba, use_container_width=True, hide_index=True)
    st.caption("YOY 컬럼은 각 2년 협약 사이클의 첫 구간에만 표기합니다.")
