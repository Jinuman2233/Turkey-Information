# =============================================================================
# app.py
# -----------------------------------------------------------------------------
# "터키 비즈니스 및 경제 동향 대시보드" 메인 실행 파일입니다.
#
# 실행 방법 (터미널에서):
#     streamlit run app.py
#
# 이 파일 하나에서 전체 화면 구성을 담당하고, 실제 데이터를 가져오는 로직은
# modules/ 폴더 안의 각 파일(fx_rates.py, policy_rate.py, minimum_wage.py,
# news_data.py, news_crawler.py)에 나누어 정리했습니다. 이렇게 "기능별로
# 파일을 나누는 것"을 모듈화(modularization)라고 하며, 코드가 길어져도
# 유지보수하기 쉬워집니다.
#
# 화면 구성 순서 (위 -> 아래):
#   1) 상단: EUR/TRY, USD/TRY, TRY/KRW 환율 카드 (각 카드 아래 최근 3개월 추이 그래프 포함)
#   2) 터키 소비자물가지수(TÜİK TÜFE/CPI) 3년 장기 추이 + 최근 12개월 MoM 표
#   3) 거시·자동차 산업 요약 (CPI/PPI 24개월, OSD 생산·수출 12개월)
#   3) 터키 기준금리 (최근 2년 월별 그래프)
#   4) 터키 최저임금
#      - 월 최저임금 (Gross, 세전 기준) + 환율 환산(EUR/USD/KRW)
#      - 시간당 최저임금 (Gross, 세전 기준, 월 255시간 근무 가정) + 환율 환산(EUR/USD/KRW)
#   5) 산업용 에너지·가스 단가 트렌드 (최근 36개월, TRY/EUR)
#   6) 터키 현지 뉴스 (실시간 자동 수집 + AI 한국어 번역, 실패 시 더미 데이터로 자동 대체)
# =============================================================================

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 우리가 modules 폴더에 나누어 만든 함수들을 가져옵니다.
from modules.fx_rates import get_all_fx_rates, get_fx_history, FX_TICKERS
from modules.cpi_data import (
    LABOR_NEGOTIATION_NOTE,
    OFFICIAL_SOURCE_LABEL,
    get_recent_mom_table,
    get_recent_mom_vertical_table,
    get_turkey_cpi_data,
)
from modules.policy_rate import get_policy_rate_dataframe, get_latest_policy_rate
from modules.minimum_wage import (
    get_minimum_wage_info,
    convert_wage_to_foreign_currencies,
    get_hourly_gross_wage_try,
    get_hourly_gross_wage_trend,
    MONTHLY_WORKING_HOURS,
)
from modules.energy_data import get_energy_price_bundle
from modules.macro_industry import get_macro_industry_bundle
from modules.news_data import get_dummy_news
from modules.news_crawler import (
    API_QUOTA_FALLBACK_MESSAGE,
    clear_news_data_caches,
    clear_news_fetch_cooldown,
    fetch_ai_translated_news,
    filter_display_news_recent,
    is_ai_translation_configured,
)


# =============================================================================
# 0. 페이지 기본 설정
# -----------------------------------------------------------------------------
# st.set_page_config()는 반드시 다른 st.* 명령어보다 "가장 먼저" 호출해야 합니다.
# layout="wide"로 설정하면 PC에서는 화면을 넓게 쓰고, 모바일에서는 자동으로
# 화면 너비에 맞춰 한 줄로 줄어드는 반응형(Responsive) 레이아웃이 됩니다.
# =============================================================================
st.set_page_config(
    page_title="터키 비즈니스 & 경제 동향 대시보드",
    page_icon="🇹🇷",
    layout="wide",  # 넓은 레이아웃: PC에서는 넓게, 모바일에서는 자동으로 좁게 표시됨
    initial_sidebar_state="collapsed",  # 모바일에서는 사이드바가 화면을 가리지 않도록 기본적으로 접어둠
)


# =============================================================================
# 1. 커스텀 CSS 적용 (카드 디자인 + 모바일 반응형 보정)
# -----------------------------------------------------------------------------
# Streamlit은 기본적으로도 화면 크기에 따라 어느 정도 자동으로 레이아웃이
# 조정되지만, 카드 느낌을 더 확실하게 주고 스마트폰에서 컬럼(가로 배치)이
# 어색하게 눌리지 않도록 아래 CSS로 세부 조정을 해줍니다.
#
# st.markdown(..., unsafe_allow_html=True) 를 사용하면 순수 HTML/CSS를
# Streamlit 화면에 직접 삽입할 수 있습니다.
# =============================================================================
st.markdown(
    """
    <style>
        /* 전체 컨텐츠 좌우 여백을 살짝 줄여서 모바일 화면을 더 넓게 활용 */
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }

        /* 섹션 제목(예: "환율 정보", "기준금리") 스타일 */
        .section-title {
            font-size: 1.35rem;
            font-weight: 700;
            margin-top: 0.6rem;
            margin-bottom: 0.6rem;
            border-left: 6px solid #C8102E; /* 터키 국기 색상(빨강) 포인트 라인 */
            padding-left: 0.6rem;
        }

        /* 카드 안의 큰 숫자(환율 값, 최저임금 값 등) */
        .big-number {
            font-size: 2.0rem;
            font-weight: 800;
            line-height: 1.2;
        }

        /* 카드 안의 작은 보조 설명 텍스트 */
        .small-caption {
            font-size: 0.85rem;
            color: #6b6b6b;
        }

        /* 뉴스 카테고리 태그(배지) 스타일 */
        .news-badge {
            display: inline-block;
            background-color: #C8102E;
            color: white;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 2px 10px;
            border-radius: 999px;
            margin-bottom: 6px;
        }

        /* --------------------------------------------------------------
           📱 모바일 반응형 보정
           화면 너비가 640px 이하(대부분의 스마트폰)일 때는
           가로로 나열된 컬럼(st.columns)을 세로로 쌓아서
           글자가 너무 작아지거나 겹치지 않도록 강제로 줄바꿈 시킵니다.
           -------------------------------------------------------------- */
        @media (max-width: 640px) {
            div[data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                width: 100% !important;
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
            .big-number {
                font-size: 1.6rem;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 헬퍼(도우미) 함수: 숫자를 보기 좋은 형태의 문자열로 바꿔줍니다.
# -----------------------------------------------------------------------------
# 값의 크기(1보다 작은지, 100보다 큰지 등)에 따라 소수점 자리수를 다르게
# 보여주면 환율처럼 숫자 크기가 다양한 데이터를 더 읽기 좋게 표현할 수 있습니다.
# =============================================================================
def format_number(value: float, decimals: int = None) -> str:
    if value is None:
        return "-"
    if decimals is not None:
        return f"{value:,.{decimals}f}"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.2f}"
    return f"{value:,.4f}"


def render_section_title(text: str):
    """섹션(구역) 제목을 통일된 스타일로 보여주는 헬퍼 함수."""
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)


def render_mini_line_chart(history, chart_key: str, line_color: str = "#C8102E", height: int = 110):
    """
    환율 카드 아래에 붙는 '작은 추이 그래프(스파크라인)'를 그리는 헬퍼 함수.

    Parameters
    ----------
    history : pandas.Series
        index=날짜, value=환율 값 (modules.fx_rates.get_fx_history()의 반환값)
    line_color : str
        그래프 선 색상
    height : int
        그래프 높이(px). 카드 안에 들어가므로 작게 설정합니다.
    """
    if history is None or history.empty:
        st.caption("⚠️ 최근 3개월 추이 데이터를 불러오지 못했습니다.")
        return

    # HEX 색상(예: "#C8102E")을 투명도가 있는 rgba() 문자열로 바꿔줍니다.
    # Plotly는 "#RRGGBBAA" 같은 8자리 HEX 표기를 지원하지 않으므로 rgba()로 변환합니다.
    hex_color = line_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    fill_color = f"rgba({r}, {g}, {b}, 0.15)"

    # -------------------------------------------------------------------
    # ⚠️ 중요: y축(세로축) 범위를 반드시 "실제 데이터의 최소~최대값" 기준으로
    # 직접 지정해 줘야 합니다.
    #
    # 환율처럼 값 자체가 0에서 한참 떨어져 있는 데이터(예: 53.xx)에
    # fill="tozeroy"(선 아래를 y=0까지 채우는 옵션)를 쓰면, Plotly가 그래프
    # 범위를 자동으로 계산할 때 "0부터 최대값까지"로 잡아버립니다.
    # 그러면 실제 등락 폭(예: 53.0~54.0)이 전체 범위(0~54)에 비해 너무 작아서
    # 그래프가 맨 위에 거의 일직선으로 눌려 보이는 문제가 생깁니다.
    # (바로 이 문제 때문에 환율 변동이 안 보이는 것처럼 보였던 것입니다.)
    #
    # 해결 방법: y축 범위를 [최솟값, 최댓값]에 위아래 여백(15%)을 더해서
    # 명시적으로(autorange를 쓰지 않고) 지정해 줍니다.
    # -------------------------------------------------------------------
    y_min = float(history.min())
    y_max = float(history.max())
    if y_max > y_min:
        padding = (y_max - y_min) * 0.15
    else:
        # 3개월 내내 값이 전혀 변하지 않은 경우(데이터가 1개뿐이거나 등락이 없는 경우)를 대비
        padding = max(abs(y_max) * 0.01, 0.0001)
    y_axis_range = [y_min - padding, y_max + padding]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history.index,
            y=history.values,
            mode="lines",
            line=dict(color=line_color, width=2),
            fill="tozeroy",
            fillcolor=fill_color,  # 선 아래를 살짝 투명하게 채워서 그래프가 더 잘 보이도록 함
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.4f}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=4, b=0),
        height=height,
        showlegend=False,
        xaxis=dict(showgrid=False, visible=False),  # 카드가 복잡해 보이지 않도록 축은 숨김
        yaxis=dict(showgrid=False, visible=False, range=y_axis_range, autorange=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(
        fig,
        width="stretch",  # 카드(컨테이너) 너비에 꽉 맞춰서 그래프를 그림
        config={"displayModeBar": False},
        key=chart_key,
    )


# =============================================================================
# 헤더(맨 위 제목) 영역
# =============================================================================
st.title("🇹🇷 터키 비즈니스 & 경제 동향 대시보드")
st.caption(
    "환율 · 소비자물가(TÜİK TÜFE) · 기준금리 · 최저임금 · 현지 뉴스를 한 화면에서 확인하세요. "
    "(환율은 yfinance, CPI는 TÜİK 공식 TÜFE, 뉴스는 구글 뉴스 자동 수집 + AI 한국어 번역 데이터입니다.)"
)

st.divider()


# =============================================================================
# 2. 섹션 1 — 환율 카드 (EUR/TRY, USD/TRY, TRY/KRW)
# -----------------------------------------------------------------------------
# yfinance에서 가져온 환율 데이터를 st.columns()를 이용해
# 3개의 카드(칸)로 나란히 배치합니다.
# 스마트폰 화면에서는 위 CSS 설정 덕분에 이 3개의 카드가 세로로 쌓여서 보입니다.
# =============================================================================
render_section_title("💱 실시간 환율")

# 데이터를 불러오는 동안 로딩 스피너(빙글빙글 도는 아이콘)를 보여줍니다.
with st.spinner("환율 정보를 불러오는 중입니다..."):
    fx_rates = get_all_fx_rates()  # {"EURTRY": {...}, "USDTRY": {...}, "TRYKRW": {...}}

# 3개의 동일한 너비의 칸(컬럼)을 만듭니다.
fx_col1, fx_col2, fx_col3 = st.columns(3)
fx_columns = [fx_col1, fx_col2, fx_col3]

for col, fx_key in zip(fx_columns, FX_TICKERS.keys()):
    info = FX_TICKERS[fx_key]
    rate = fx_rates.get(fx_key)

    with col:
        # st.container(border=True)를 사용하면 테두리가 있는 '카드' 모양의 상자가 생깁니다.
        with st.container(border=True):
            st.markdown(f"**{info['label']}**")

            if rate is None:
                # 인터넷 연결 문제 등으로 데이터를 못 가져온 경우를 대비한 안내 문구
                st.markdown("<div class='big-number'>데이터 없음</div>", unsafe_allow_html=True)
                st.caption("⚠️ 환율 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            else:
                current = rate["current"]
                change = rate["change"]
                change_pct = rate["change_pct"]

                # 전일 대비 상승이면 빨간색(▲), 하락이면 파란색(▼)으로 표시합니다.
                if change > 0:
                    delta_color = "#C8102E"
                    arrow = "▲"
                elif change < 0:
                    delta_color = "#1565C0"
                    arrow = "▼"
                else:
                    delta_color = "#6b6b6b"
                    arrow = "-"

                st.markdown(
                    f"<div class='big-number'>{format_number(current)}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<span style='color:{delta_color}; font-weight:600;'>"
                    f"{arrow} {format_number(abs(change))} ({change_pct:+.2f}%)"
                    f"</span> <span class='small-caption'>전일 대비</span>",
                    unsafe_allow_html=True,
                )

                # ---------------------------------------------------------------
                # 카드 안, 현재 환율 값 바로 아래에 "최근 3개월 추이" 미니 그래프를
                # 추가로 보여줍니다. 그래프가 큰 숫자보다 시선을 뺏지 않도록
                # 축/범례를 모두 숨긴 단순한 라인(스파크라인) 형태로 그립니다.
                # ---------------------------------------------------------------
                st.markdown(
                    "<span class='small-caption'>최근 3개월 추이</span>",
                    unsafe_allow_html=True,
                )
                with st.spinner("추이 데이터 불러오는 중..."):
                    history_3mo = get_fx_history(fx_key, period="3mo")
                render_mini_line_chart(
                    history_3mo,
                    chart_key=f"fx_mini_chart_{fx_key}",
                    line_color=delta_color if change != 0 else "#C8102E",
                )

st.caption("데이터 출처: Yahoo Finance (yfinance) · 5분마다 자동 갱신")

st.divider()


# =============================================================================
# 3. 섹션 2 — 터키 소비자물가지수(TÜİK TÜFE / CPI) 3년 장기 추이
# -----------------------------------------------------------------------------
# 환율 카드 바로 아래, 기준금리 섹션 바로 위에 배치합니다.
# modules/cpi_data.py 에서 TÜİK 공식 TÜFE를 우선 수집하고,
# YoY / MoM 상승률·최근 12개월 MoM 표를 보여줍니다.
# =============================================================================
render_section_title("📈 터키 소비자물가지수 (TÜİK TÜFE / CPI) 3년 장기 추이")
st.caption(f"공식 출처: {OFFICIAL_SOURCE_LABEL}")
st.info(LABOR_NEGOTIATION_NOTE)

with st.spinner("TÜİK TÜFE(소비자물가지수) 데이터를 불러오는 중입니다..."):
    cpi_data = get_turkey_cpi_data()

cpi_df = cpi_data["df"]
latest_yoy = cpi_data["latest_yoy"]
latest_mom = cpi_data["latest_mom"]
yoy_change = cpi_data["yoy_change"]
latest_cpi_month = cpi_data["latest_month"]

if cpi_df is None or cpi_df.empty or latest_yoy is None:
    st.warning("⚠️ 터키 CPI(TÜFE) 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
else:
    # 3-1) 핵심 지표 카드 3열: YoY / MoM / YoY 변동폭(%p) — 기존 유지
    yoy_col, mom_col, chg_col = st.columns(3)

    with yoy_col:
        st.metric(
            label="전년 동기 대비 (YoY)",
            value=f"{latest_yoy:.2f}%",
            delta=f"{yoy_change:+.2f}%p 전월비",
            delta_color="inverse",  # 물가는 상승이 부담 → 상승을 붉게
            help="가장 최근 달의 전년 동기 대비 소비자물가 상승률입니다.",
        )

    with mom_col:
        st.metric(
            label="전월 대비 (MoM)",
            value=f"{latest_mom:.2f}%",
            help="가장 최근 달의 전월 대비 소비자물가 상승률입니다.",
        )

    with chg_col:
        # YoY 변동폭이 음수면 상승세 둔화, 양수면 가속
        if yoy_change < 0:
            trend_label = "상승세 둔화"
        elif yoy_change > 0:
            trend_label = "상승세 가속"
        else:
            trend_label = "전월과 동일"
        st.metric(
            label="YoY 변동폭 (전월 대비)",
            value=f"{yoy_change:+.2f}%p",
            delta=trend_label,
            delta_color="off",
            help="전월 대비 연간 물가상승률(YoY)이 얼마나 변했는지(%p)입니다.",
        )

    st.caption(f"기준월: {latest_cpi_month}")

    # 3-2) 최근 12개월 MoM 테이블 (3년 장기 차트 바로 위)
    # 임금 인상률·물가상승분 누적 변동을 월별로 직관적으로 확인하기 위한 표입니다.
    st.markdown("**최근 12개월 전월 대비 물가상승률 (MoM %)**")
    mom_wide = get_recent_mom_table(cpi_df, months=12)
    mom_vertical = get_recent_mom_vertical_table(cpi_df, months=12)
    if not mom_wide.empty:
        st.dataframe(mom_wide, width="stretch")
    if not mom_vertical.empty:
        # 모바일 등에서 가로표가 잘릴 때를 대비한 세로형 보조 표
        with st.expander("세로형으로 보기 (연-월 / MoM %)", expanded=False):
            st.dataframe(mom_vertical, width="stretch", hide_index=True)

    # 3-3) 복합 차트: YoY 꺾은선(주축) + MoM 막대(보조축)
    fig_cpi = make_subplots(specs=[[{"secondary_y": True}]])

    # 배경 막대: 월간 물가상승률(MoM %) — 연한 색으로 보조 정보
    fig_cpi.add_trace(
        go.Bar(
            x=cpi_df["날짜"],
            y=cpi_df["MoM(%)"],
            customdata=cpi_df[["YoY(%)", "MoM(%)"]],
            name="MoM (%)",
            marker=dict(color="rgba(21, 101, 192, 0.28)"),
            hovertemplate=(
                "%{x|%Y-%m}<br>"
                "YoY: %{customdata[0]:.2f}%<br>"
                "MoM: %{customdata[1]:.2f}%<extra></extra>"
            ),
        ),
        secondary_y=True,
    )

    # 전경 꺾은선: 연간 물가상승률(YoY %) — 굵고 명확하게
    fig_cpi.add_trace(
        go.Scatter(
            x=cpi_df["날짜"],
            y=cpi_df["YoY(%)"],
            customdata=cpi_df[["YoY(%)", "MoM(%)"]],
            mode="lines+markers",
            name="YoY (%)",
            line=dict(color="#C8102E", width=3.5),
            marker=dict(size=5, color="#C8102E"),
            hovertemplate=(
                "%{x|%Y-%m}<br>"
                "YoY: %{customdata[0]:.2f}%<br>"
                "MoM: %{customdata[1]:.2f}%<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    fig_cpi.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        autosize=True,
        barmode="relative",
    )
    fig_cpi.update_xaxes(title_text=None, tickformat="%Y-%m")
    fig_cpi.update_yaxes(title_text="연간 물가상승률 YoY (%)", secondary_y=False)
    fig_cpi.update_yaxes(title_text="월간 물가상승률 MoM (%)", secondary_y=True, showgrid=False)

    st.plotly_chart(fig_cpi, width="stretch", config={"displayModeBar": False})

    if cpi_data.get("is_dummy"):
        st.caption(
            "⚠️ 실시간 수집에 실패해 TÜİK 공식 발표치를 반영한 오프라인 폴백 데이터를 표시 중입니다. "
            f"(수집 경로: {cpi_data.get('source', 'fallback')} · 하루 1회 갱신 시도)"
        )
    else:
        st.caption(
            f"데이터 출처: {OFFICIAL_SOURCE_LABEL} · 수집: {cpi_data.get('source', 'TÜİK')} · 하루 1회 자동 갱신"
        )

st.divider()


# =============================================================================
# 3-B. 거시경제 · 자동차 산업 동향 요약 (고밀도: 탭)
# -----------------------------------------------------------------------------
# modules/macro_industry.py
#   탭1) TÜİK CPI vs PPI YoY 24개월 (생산원가 vs 소비자물가 갭)
#   탭2) OSD 최근 12개월 생산(막대) · 수출(선) + 최신월 메트릭
# =============================================================================
render_section_title("🏭 거시경제 · 자동차 산업 동향 요약")

try:
    with st.spinner("거시·자동차 산업 동향을 불러오는 중입니다..."):
        macro_bundle = get_macro_industry_bundle()
    inflation = macro_bundle["inflation"]
    auto = macro_bundle["auto"]

    tab_prices, tab_osd = st.tabs(["물가 동향 (CPI / PPI)", "자동차 산업 (OSD)"])

    with tab_prices:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("CPI YoY", f"{inflation['latest_cpi']:.2f}%", help="소비자물가 전년 동기 대비")
        with m2:
            st.metric("PPI YoY", f"{inflation['latest_ppi']:.2f}%", help="생산자물가 전년 동기 대비")
        with m3:
            st.metric(
                "갭 (CPI−PPI)",
                f"{inflation['latest_gap']:+.2f}%p",
                help="양수면 소비자물가가 생산자물가보다 높음",
            )
        st.plotly_chart(
            inflation["figure"],
            width="stretch",
            config={"displayModeBar": False},
        )
        cap = f"기준월 {inflation['latest_month']} · {inflation['source']} · 최근 24개월"
        if inflation.get("is_dummy"):
            st.caption(f"⚠️ {cap} (일부/전부 더미 폴백)")
        else:
            st.caption(cap)

    with tab_osd:
        o1, o2, o3 = st.columns(3)
        with o1:
            st.metric(
                f"총 생산량 ({auto['latest_month']})",
                f"{auto['latest_production']:,}대",
            )
        with o2:
            st.metric(
                f"수출량 ({auto['latest_month']})",
                f"{auto['latest_export']:,}대",
            )
        with o3:
            st.metric(
                "생산 전년 동월 대비",
                f"{auto['production_yoy']:+.1f}%",
                delta=f"수출 {auto['export_yoy']:+.1f}%",
            )
        st.plotly_chart(
            auto["figure"],
            width="stretch",
            config={"displayModeBar": False},
        )
        cap = f"{auto['source']} · 최근 12개월 생산(막대) / 수출(선)"
        if auto.get("is_dummy"):
            st.caption(f"⚠️ {cap} (OSD 수집 실패 시 월 10~15만 대 규모 더미)")
        else:
            st.caption(cap)
except Exception:
    st.caption("⚠️ 거시·자동차 산업 요약 데이터를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")

st.divider()


# =============================================================================
# 4. 섹션 3 — 터키 기준금리 (최근 2년 월별 추이)
# -----------------------------------------------------------------------------
# modules/policy_rate.py 에서 만들어 둔 데이터를 그래프로 표현합니다.
# Plotly 라이브러리를 사용하면 마우스를 올렸을 때 값이 보이는(hover) 등
# 인터랙티브한 그래프를 쉽게 만들 수 있고, 스마트폰에서도 손가락으로
# 확대/이동하며 볼 수 있습니다.
# =============================================================================
render_section_title("🏦 터키 기준금리 (최근 2년, 월별)")

latest_rate_info = get_latest_policy_rate()
rate_df = get_policy_rate_dataframe(months=24)

# 3-1) 현재 기준금리를 큰 숫자(메트릭)로 먼저 보여줍니다.
metric_col1, metric_col2 = st.columns([1, 2])
with metric_col1:
    with st.container(border=True):
        st.markdown("**현재 기준금리 (1주일물 레포금리)**")
        st.markdown(
            f"<div class='big-number'>{latest_rate_info['rate']:.2f}%</div>",
            unsafe_allow_html=True,
        )
        change = latest_rate_info["change"]
        change_text = f"{change:+.2f}%p" if change != 0 else "변동 없음"
        st.caption(f"기준월: {latest_rate_info['month']} · 전월 대비 {change_text}")

with metric_col2:
    # Plotly로 선(line) + 마커(marker) 그래프를 그립니다.
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=rate_df["날짜"],
            y=rate_df["기준금리(%)"],
            mode="lines+markers",
            line=dict(color="#C8102E", width=3),
            marker=dict(size=6),
            name="터키 기준금리",
            hovertemplate="%{x|%Y-%m}<br>기준금리: %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=280,
        yaxis_title="기준금리 (%)",
        xaxis_title=None,
        showlegend=False,
        # 모바일에서도 그래프가 화면 너비에 맞춰 자동으로 줄어들도록 설정
        autosize=True,
    )
    # width="stretch" 로 두면 화면(컨테이너) 너비에 맞춰 그래프가 자동으로 늘어나거나 줄어듭니다.
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.caption(
    "⚠️ 기준금리 데이터는 참고용 샘플 데이터입니다. 실제 서비스에서는 터키 중앙은행(TCMB)의 "
    "공개 데이터 시스템(EVDS) API 등으로 교체하는 것을 권장합니다."
)

st.divider()


# =============================================================================
# 5. 섹션 4 — 터키 최저임금 + 환율 환산
# -----------------------------------------------------------------------------
# modules/minimum_wage.py 가 웹에서 최신 Gross Asgari Ücret을 자동 수집하고,
# 위에서 가져온 환율(fx_rates)로 EUR / USD / KRW 환산까지 연결합니다.
#
# 5-1) 월 최저임금 : Gross(세전) 기준으로 표시 + 적용/발표일
# 5-2) 시간당 최저임금 : Gross(세전) 기준으로 표시 (월 근무시간 255시간 기준)
# =============================================================================
render_section_title("💰 터키 최저임금 (Gross, 세전 기준)")

# modules/minimum_wage.py 가 CSGB 등에서 최신 Gross Asgari Ücret을 자동 수집합니다.
# (하루 1회 캐시, 실패 시 2026년 공식 기준 폴백)
with st.spinner("최신 세전 최저임금(Gross Asgari Ücret)을 불러오는 중입니다..."):
    wage_info = get_minimum_wage_info()

gross_wage_try = wage_info["gross_wage_try"]
effective_label = wage_info.get("effective_period") or (
    f"적용/발표일: {wage_info.get('effective_year', 2026)}년 "
    f"{int(wage_info.get('effective_month', 1)):02d}월"
)

# 환율을 이용해 '월 Gross 최저임금'을 외화로 환산합니다.
gross_converted = convert_wage_to_foreign_currencies(gross_wage_try, fx_rates)

wage_col1, wage_col2, wage_col3, wage_col4 = st.columns(4)

with wage_col1:
    with st.container(border=True):
        st.markdown("**월 최저임금 (TRY, Gross)**")
        st.markdown(
            f"<div class='big-number'>₺ {format_number(gross_wage_try, 0)}</div>",
            unsafe_allow_html=True,
        )
        st.caption(effective_label)

with wage_col2:
    with st.container(border=True):
        st.markdown("**≈ EUR (유로)**")
        eur_value = gross_converted["EUR"]
        display_value = f"€ {format_number(eur_value, 0)}" if eur_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption(effective_label)

with wage_col3:
    with st.container(border=True):
        st.markdown("**≈ USD (달러)**")
        usd_value = gross_converted["USD"]
        display_value = f"$ {format_number(usd_value, 0)}" if usd_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption(effective_label)

with wage_col4:
    with st.container(border=True):
        st.markdown("**≈ KRW (원)**")
        krw_value = gross_converted["KRW"]
        display_value = f"₩ {format_number(krw_value, 0)}" if krw_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption(effective_label)

st.caption(
    "데이터 출처: 터키 노동사회보장부(CSGB) Asgari Ücret 자동 수집 · 하루 1회 갱신 "
    "(실패 시 TradingEconomics/현지 포털·2026년 공식 기준 폴백)"
)

# -----------------------------------------------------------------------------
# 5-2) 시간당 최저임금 (Gross, 세전 기준)
# -----------------------------------------------------------------------------
# 위에서 수집한 '월 Gross(세전) 최저임금'을 '월 근무시간(255시간)'으로 나누어
# 시간당 금액을 구하고, 동일하게 EUR / USD / KRW로 환산합니다.
# -----------------------------------------------------------------------------
st.markdown(
    f"<div style='margin-top:0.8rem; font-weight:700;'>⏱️ 시간당 최저임금 "
    f"(Gross, 세전 기준 · 월 {MONTHLY_WORKING_HOURS}시간 근무)</div>",
    unsafe_allow_html=True,
)

hourly_gross_wage_try = get_hourly_gross_wage_try(monthly_hours=MONTHLY_WORKING_HOURS)
hourly_converted = convert_wage_to_foreign_currencies(hourly_gross_wage_try, fx_rates)

hourly_col1, hourly_col2, hourly_col3, hourly_col4 = st.columns(4)

with hourly_col1:
    with st.container(border=True):
        st.markdown("**시간당 최저임금 (TRY, Gross)**")
        st.markdown(
            f"<div class='big-number'>₺ {format_number(hourly_gross_wage_try, 2)}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"월 {format_number(gross_wage_try, 0)} TRY ÷ {MONTHLY_WORKING_HOURS}시간 · {effective_label}"
        )

with hourly_col2:
    with st.container(border=True):
        st.markdown("**≈ EUR (유로)**")
        hourly_eur = hourly_converted["EUR"]
        display_value = f"€ {format_number(hourly_eur, 2)}" if hourly_eur else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 EUR/TRY 환율 기준")

with hourly_col3:
    with st.container(border=True):
        st.markdown("**≈ USD (달러)**")
        hourly_usd = hourly_converted["USD"]
        display_value = f"$ {format_number(hourly_usd, 2)}" if hourly_usd else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 USD/TRY 환율 기준")

with hourly_col4:
    with st.container(border=True):
        st.markdown("**≈ KRW (원)**")
        hourly_krw = hourly_converted["KRW"]
        display_value = f"₩ {format_number(hourly_krw, 0)}" if hourly_krw else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 TRY/KRW 환율 기준")

# -----------------------------------------------------------------------------
# 5-3) 최근 5년 시간당 Gross 최저임금 추이 (TRY / EUR / USD)
# -----------------------------------------------------------------------------
st.markdown(
    "<div style='margin-top:1rem; font-weight:700;'>📈 최근 5년 시간당 Gross 최저임금 추이 "
    "(TRY · EUR · USD)</div>",
    unsafe_allow_html=True,
)
try:
    wage_trend = get_hourly_gross_wage_trend(monthly_hours=MONTHLY_WORKING_HOURS)
    st.plotly_chart(
        wage_trend["figure"],
        width="stretch",
        config={"displayModeBar": False},
    )
    if wage_trend.get("is_fx_fallback"):
        st.caption(
            f"⚠️ {wage_trend.get('source', '')} "
            "(환율 실시간 수집 실패 시 mock 월평균 환율 폴백 사용)"
        )
    else:
        st.caption(wage_trend.get("source", ""))
    st.caption(
        "TRY 선 위 숫자(+%)는 이전 월 대비 시간당 Gross 인상률입니다. "
        "EUR/USD는 해당 월 평균 환율로 환산한 값입니다."
    )
except Exception:
    st.caption("⚠️ 최저임금 5년 추이 차트를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")

st.divider()


# =============================================================================
# 6. 섹션 5 — 산업용 에너지 및 가스 단가 트렌드 (최근 36개월)
# -----------------------------------------------------------------------------
# modules/energy_data.py 독립 모듈:
#   - Mock 월말 단가(전기/가스/질소/헬륨) + yfinance 월말 EUR/TRY 종가로 EUR 환산
#   - 차트(EUR) → 통합 테이블(TRY/EUR) 순으로 표시
# =============================================================================
render_section_title("⚡ 산업용 에너지 및 가스 단가 트렌드 (최근 36개월)")

try:
    energy_bundle = get_energy_price_bundle()
    st.plotly_chart(
        energy_bundle["figure"],
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(
        "EUR 단가 추이 · 전기/가스/질소는 왼쪽 축, 헬륨(고가)은 오른쪽 축입니다."
    )
    st.dataframe(
        energy_bundle["display_table"],
        width="stretch",
        hide_index=True,
    )
    if energy_bundle.get("is_fx_fallback"):
        st.caption(
            f"⚠️ {energy_bundle.get('source', '')} "
            "(월말 환율 일부/전부는 mock 폴백입니다. 단가는 엑셀 업로드로 교체 가능)"
        )
    else:
        st.caption(energy_bundle.get("source", ""))
    st.caption(
        "단위 참고: 전기 TRY·EUR/kWh · 가스 TRY·EUR/Sm³ · 질소·헬륨 TRY·EUR/Nm³ · 소수점 2자리"
    )
except Exception:
    st.caption("⚠️ 산업용 에너지/가스 단가 데이터를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")

st.divider()


# =============================================================================
# 7. 섹션 6 — 터키 현지 뉴스 (실시간 자동 수집 + AI 한국어 번역)
# -----------------------------------------------------------------------------
# modules/news_crawler.py 에서 다음과 같은 순서로 뉴스를 준비해 옵니다.
#   1) feedparser로 구글 뉴스(Google News) RSS에서 터키 자동차 산업
#      (otomotiv / otomobil ihracatı / araç üretimi / TOGG 등) 기사를 수집
#      → when:30d + Python datetime 이중 필터로 최근 30일만 유지 → 최신순 상위 N개
#   2) Google Gemini REST API(gemini-3.5-flash)로 기사들을 배치(1~2회) 번역
#   3) 결과를 12시간 동안 캐시(@st.cache_data)해서 API 비용과 로딩 시간을 절약
#
# API 키가 설정되어 있지 않거나(테스트 환경 등) 네트워크/번역에 실패하면,
# modules/news_data.py 의 더미 데이터로 자동 대체(fallback)해서 화면이
# 비어 보이지 않도록 합니다. -> 이렇게 하면 기존에 만들어 둔 더미 데이터 코드를
# 하나도 지우거나 수정하지 않고, "새로운 실데이터 모듈"만 추가로 연결할 수 있습니다.
#
# [메인 화면 UI]
#   - '한국어로 번역된 기사 제목' 목록만 깔끔하게 보여줍니다 (st.expander의
#     접힌 상태 라벨을 제목으로 사용).
# [제목을 클릭해서 펼쳤을 때(expander 내부) UI]
#   - 카테고리 · 발행 일시(Published Date) · 출처
#   - 한국어로 번역/요약된 기사 본문(3줄 요약)
#   - 🔗 원문 기사로 이동하는 링크 (새 창에서 열림)
# =============================================================================
render_section_title("📰 터키 자동차 산업 뉴스 (AI 한국어 번역)")

# 새로고침은 RSS 화면만 갱신합니다. 24시간 번역 캐시는 지우지 않아
# 무료 할당량(하루 ~20회)을 보호합니다.
refresh_col1, refresh_col2 = st.columns([3, 1])
with refresh_col2:
    if st.button("🔄 화면 새로고침", key="refresh_automotive_news"):
        clear_news_fetch_cooldown()
        # 번역 캐시는 유지 (clear_news_data_caches는 RSS만 비움)
        clear_news_data_caches()
        st.rerun()

ai_ready = is_ai_translation_configured()
news_mode = "empty"
is_dummy_news = False

if ai_ready:
    try:
        news_result = fetch_ai_translated_news()
    except Exception:
        news_result = {
            "news": [],
            "error": API_QUOTA_FALLBACK_MESSAGE,
            "cooldown_remaining": 0,
            "error_kind": "other",
            "news_mode": "empty",
        }

    news_list = news_result.get("news") or []
    news_error = news_result.get("error")
    news_mode = news_result.get("news_mode") or ("live" if news_list else "empty")

    # ★ 통신/할당량 오류 시: 빨간 st.error 금지 → warning + 원문 리스트
    if news_error:
        st.warning(API_QUOTA_FALLBACK_MESSAGE)

    news_list = filter_display_news_recent(news_list)

    if news_list:
        is_dummy_news = False
    else:
        news_list = get_dummy_news()
        is_dummy_news = True
else:
    st.info(
        "💡 AI 번역 기능을 사용하려면 Gemini API 키(GEMINI_API_KEY)를 설정해 주세요. "
        "설정 전까지는 예시(더미) 뉴스를 표시합니다.\n\n"
        "Streamlit Cloud: App settings → Secrets 에 "
        '`GEMINI_API_KEY = "AIza..."` 를 추가한 뒤 **Reboot** 해 주세요.'
    )
    news_list = get_dummy_news()
    is_dummy_news = True

news_list = filter_display_news_recent(news_list) if not is_dummy_news else news_list
if not news_list and not is_dummy_news:
    news_list = get_dummy_news()
    is_dummy_news = True

# 메인 화면에는 "제목 리스트"만 깔끔하게 보이도록, st.expander의 라벨(닫혀 있을 때
# 보이는 글자)에 번역된 한국어 제목만 넣습니다. 클릭해서 펼쳤을 때만 요약/링크가 보입니다.
for news in news_list:
    with st.expander(f"📰 {news['title_kr']}"):
        # 펼쳤을 때 맨 위에 카테고리·날짜·출처를 작은 글씨로 보여줍니다.
        st.markdown(
            f"<span class='news-badge'>{news['category']}</span> "
            f"<span class='small-caption'>발행 일시 (Published): {news.get('date', '날짜 미상')} · {news.get('source', '')}</span>",
            unsafe_allow_html=True,
        )

        # 한국어로 번역/요약된 기사 본문(3줄 요약)을 불릿(•) 형태로 보여줍니다.
        for line in news["summary_kr"]:
            st.markdown(f"- {line}")

        st.markdown("")  # 약간의 여백

        # 🔗 원문 기사 링크 — st.link_button은 클릭하면 항상 새 창(새 탭)에서 열립니다.
        if news.get("link"):
            st.link_button("🔗 원문 기사 보기 (새 창에서 열림)", news["link"])
        else:
            st.caption("원문 링크가 제공되지 않는 데이터입니다.")

if is_dummy_news:
    st.caption("⚠️ 현재 표시 중인 뉴스는 레이아웃 확인용 예시(더미) 데이터입니다.")
elif news_mode == "rss_only":
    st.caption("데이터 출처: Google News RSS 원문 (AI 번역 한도/오류로 미번역) · 추가 API 호출 없음")
elif news_mode == "stale_cache":
    st.caption("데이터 출처: 이전 성공 번역 캐시 · 추가 API 호출 없음")
else:
    st.caption(
        "데이터 출처: Google News RSS(터키 자동차 산업 · 최근 30일) "
        "+ Gemini 3.5 Flash-Lite 일괄 번역(1회/24시간 캐시)"
    )

st.divider()

# =============================================================================
# 푸터(맨 아래 안내 문구)
# =============================================================================
st.caption(
    "본 대시보드의 환율 정보는 Yahoo Finance(yfinance) 데이터를 기반으로 하며, "
    "투자/거래 판단의 참고 자료일 뿐 공식 금융 정보로 사용할 수 없습니다. "
    "뉴스 섹션은 Google News RSS 원문을 AI로 번역한 결과이므로, 중요한 의사결정 전에는 "
    "반드시 원문 기사를 통해 사실관계를 다시 확인해 주세요."
)
