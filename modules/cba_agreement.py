# =============================================================================
# cba_agreement.py
# -----------------------------------------------------------------------------
# MESS ↔ Türk Metal 단체협약(CBA) 인상률과 물가(인플레이션) 비교 모듈입니다.
#
# 데이터는 2년 협약 주기를 6개월 단위로 나눈 확정 시계열입니다.
# 수치는 임의로 바꾸지 않습니다.
# =============================================================================

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CHART_HEIGHT = 240
CHART_MARGIN = dict(t=25, b=10, l=10, r=10)
CBA_CYCLE_START_ROWS = (0, 4, 8, 12)
CBA_HIGHLIGHT_COLOR = "#e6f2ff"

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
}


def get_cba_dataframe() -> pd.DataFrame:
    """MESS-Türk Metal 6개월 구간 CBA/물가 확정 테이블."""
    return pd.DataFrame(CBA_DATA)


def highlight_rows(row: pd.Series) -> list[str]:
    """2년 협약 주기 첫 행(2019/2021/2023/2025 Sep)을 연한 파란색으로 표시."""
    if row.name in CBA_CYCLE_START_ROWS:
        return [f"background-color: {CBA_HIGHLIGHT_COLOR}"] * len(row)
    return [""] * len(row)


def style_cba_dataframe(df: pd.DataFrame):
    return df.style.apply(highlight_rows, axis=1).format(
        {
            "Inflation (%)": "{:.2f}",
            "CBA (%)": "{:.2f}",
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


def render_cba_agreement_section() -> None:
    """최저임금 바로 위에 두는 MESS-Türk Metal CBA 차트+표."""
    df_cba = get_cba_dataframe()
    st.markdown(
        "<div class='section-title'>📑 MESS · Türk Metal 단체협약 (CBA) 인상률</div>",
        unsafe_allow_html=True,
    )
    st.caption("6개월 구간 물가 vs CBA 인상률")

    st.markdown("**6개월 주기 인상률 추이**")
    st.plotly_chart(
        build_cba_period_figure(df_cba),
        width="stretch",
        config={"displayModeBar": False},
    )

    styled_df = df_cba.style.apply(highlight_rows, axis=1).format(
        {
            "Inflation (%)": "{:.2f}",
            "CBA (%)": "{:.2f}",
        }
    )
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    st.caption("연한 파란색 행은 새로운 2년 단체협약이 시작되는 구간입니다.")
