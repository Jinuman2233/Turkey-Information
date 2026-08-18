# =============================================================================
# app.py
# -----------------------------------------------------------------------------
# 터키 비즈니스 & 경제 동향 대시보드 — 1페이지 고밀도 와이드 그리드.
# 데이터 로직은 modules/ 에 두고, 이 파일은 배치·차트 사이즈만 담당합니다.
#
# Row 1 (3:7)  환율·기준금리 | AI 뉴스(최대 5건, 스크롤)
# Row 2 (5:5)  최저임금 5년 추이 | CPI·PPI YoY
# Row 3 (6:4)  에너지/가스 단가 | OSD 생산·수출
# =============================================================================

import streamlit as st
import plotly.graph_objects as go

from modules.fx_rates import get_all_fx_rates, get_fx_history, FX_TICKERS
from modules.policy_rate import get_latest_policy_rate
from modules.minimum_wage import get_hourly_gross_wage_trend, MONTHLY_WORKING_HOURS
from modules.energy_data import get_energy_price_bundle
from modules.macro_industry import get_macro_industry_bundle
from modules.news_data import get_dummy_news
from modules.news_crawler import (
    API_QUOTA_FALLBACK_MESSAGE,
    fetch_ai_translated_news,
    filter_display_news_recent,
    is_ai_translation_configured,
)

NEWS_DISPLAY_LIMIT = 5
CHART_HEIGHT = 350
CHART_MARGIN = dict(t=30, b=10, l=10, r=10)

st.set_page_config(
    page_title="터키 비즈니스 & 경제 동향 대시보드",
    page_icon="🇹🇷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        html, body, [data-testid="stAppViewContainer"] { overflow-x: hidden; }
        .block-container {
            padding-top: 0.45rem !important;
            padding-bottom: 0.8rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        header[data-testid="stHeader"] { background: transparent; }
        div[data-testid="stToolbar"] { display: none; }
        h1 { font-size: 1.35rem !important; margin: 0 0 0.15rem 0 !important; padding: 0 !important; }
        .stCaption, [data-testid="stCaptionContainer"] { margin-top: 0 !important; margin-bottom: 0.15rem !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.5rem !important; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { padding: 0 0.15rem !important; }
        hr { margin: 0.25rem 0 !important; }
        .stPlotlyChart { margin: 0 !important; }
        [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
        div[data-testid="stExpander"] { margin-bottom: 0.15rem !important; }
        .section-title {
            font-size: 0.95rem;
            font-weight: 700;
            margin: 0 0 0.2rem 0;
            border-left: 4px solid #C8102E;
            padding-left: 0.45rem;
            line-height: 1.25;
        }
        .big-number { font-size: 1.25rem; font-weight: 800; line-height: 1.15; }
        .small-caption { font-size: 0.75rem; color: #6b6b6b; }
        .news-badge {
            display: inline-block;
            background-color: #C8102E;
            color: white;
            font-size: 0.68rem;
            font-weight: 600;
            padding: 1px 8px;
            border-radius: 999px;
            margin-right: 6px;
        }
        @media (max-width: 900px) {
            div[data-testid="stHorizontalBlock"] { flex-direction: column !important; }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)


def apply_report_chart_size(fig, height: int = CHART_HEIGHT):
    """모듈 Figure의 데이터는 유지하고, 1페이지용 높이·여백만 app.py에서 맞춥니다."""
    if fig is None:
        return None
    fig.update_layout(height=height, margin=CHART_MARGIN, autosize=True)
    return fig


def render_mini_line_chart(history, chart_key: str, line_color: str = "#C8102E", height: int = 56):
    if history is None or getattr(history, "empty", True):
        return
    hex_color = line_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    fill_color = f"rgba({r}, {g}, {b}, 0.15)"
    y_min = float(history.min())
    y_max = float(history.max())
    padding = (y_max - y_min) * 0.15 if y_max > y_min else max(abs(y_max) * 0.01, 0.0001)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history.index,
            y=history.values,
            mode="lines",
            line=dict(color=line_color, width=1.6),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.4f}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=2, b=0),
        height=height,
        showlegend=False,
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(showgrid=False, visible=False, range=[y_min - padding, y_max + padding], autorange=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=chart_key)


def load_news_list() -> tuple[list, str, bool]:
    """뉴스 리스트, 모드, 더미 여부."""
    if not is_ai_translation_configured():
        return get_dummy_news(), "empty", True
    try:
        news_result = fetch_ai_translated_news()
    except Exception:
        news_result = {"news": [], "error": API_QUOTA_FALLBACK_MESSAGE, "news_mode": "empty"}
    news_list = news_result.get("news") or []
    news_error = news_result.get("error")
    news_mode = news_result.get("news_mode") or ("live" if news_list else "empty")
    if news_error:
        st.caption(f"⚠️ {API_QUOTA_FALLBACK_MESSAGE}")
    news_list = filter_display_news_recent(news_list)
    if not news_list:
        return get_dummy_news(), news_mode, True
    return news_list[:NEWS_DISPLAY_LIMIT], news_mode, False


# -----------------------------------------------------------------------------
# 데이터 로드 (모듈 로직 변경 없음)
# -----------------------------------------------------------------------------
st.markdown("### 🇹🇷 터키 비즈니스 & 경제 동향")
st.caption("1페이지 고밀도 그리드 · 향후 PDF/Excel 추출용 레이아웃")

with st.spinner("대시보드 데이터를 불러오는 중입니다..."):
    fx_rates = get_all_fx_rates()
    latest_rate_info = get_latest_policy_rate()
    try:
        wage_trend = get_hourly_gross_wage_trend(monthly_hours=MONTHLY_WORKING_HOURS)
    except Exception:
        wage_trend = None
    try:
        macro_bundle = get_macro_industry_bundle()
    except Exception:
        macro_bundle = None
    try:
        energy_bundle = get_energy_price_bundle()
    except Exception:
        energy_bundle = None
    news_list, news_mode, is_dummy_news = load_news_list()


# =============================================================================
# Row 1 — 3:7  환율·기준금리 | AI 뉴스
# =============================================================================
row1_left, row1_right = st.columns([3, 7], gap="small")

with row1_left:
    render_section_title("💱 환율 · 🏦 기준금리")
    fx_c1, fx_c2, fx_c3 = st.columns(3)
    for col, fx_key in zip((fx_c1, fx_c2, fx_c3), FX_TICKERS.keys()):
        info = FX_TICKERS[fx_key]
        rate = fx_rates.get(fx_key)
        with col:
            with st.container(border=True):
                short_label = info["label"].split("(")[0].strip()
                st.markdown(f"**{short_label}**")
                if rate is None:
                    st.markdown("<div class='big-number'>-</div>", unsafe_allow_html=True)
                else:
                    current = rate["current"]
                    change = rate["change"]
                    change_pct = rate["change_pct"]
                    if change > 0:
                        delta_color, arrow = "#C8102E", "▲"
                    elif change < 0:
                        delta_color, arrow = "#1565C0", "▼"
                    else:
                        delta_color, arrow = "#6b6b6b", "-"
                    st.markdown(
                        f"<div class='big-number'>{format_number(current)}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<span style='color:{delta_color}; font-weight:600; font-size:0.78rem;'>"
                        f"{arrow} {change_pct:+.2f}%</span>",
                        unsafe_allow_html=True,
                    )
                    history_3mo = get_fx_history(fx_key, period="3mo")
                    render_mini_line_chart(
                        history_3mo,
                        chart_key=f"fx_mini_{fx_key}",
                        line_color=delta_color if change != 0 else "#C8102E",
                    )

    with st.container(border=True):
        change = latest_rate_info.get("change") or 0
        change_text = f"{change:+.2f}%p" if change != 0 else "변동 없음"
        st.metric(
            "기준금리 (1주 레포)",
            f"{latest_rate_info['rate']:.2f}%",
            delta=f"{latest_rate_info['month']} · {change_text}",
        )

with row1_right:
    render_section_title("📰 터키 자동차 산업 뉴스 (AI 번역 · 최신 5건)")
    with st.container(height=360, border=True):
        for news in news_list:
            with st.expander(f"{news.get('title_kr', '(제목 없음)')}", expanded=False):
                st.markdown(
                    f"<span class='news-badge'>{news.get('category', '')}</span>"
                    f"<span class='small-caption'>발행 일시: {news.get('date', '날짜 미상')} · {news.get('source', '')}</span>",
                    unsafe_allow_html=True,
                )
                for line in news.get("summary_kr") or []:
                    st.markdown(f"- {line}")
                if news.get("link"):
                    st.link_button("원문 보기", news["link"])
    if is_dummy_news:
        st.caption("⚠️ 예시(더미) 뉴스")
    elif news_mode == "rss_only":
        st.caption("원문 RSS (미번역)")
    else:
        st.caption("Google News + Gemini Flash-Lite · 24시간 캐시")


# =============================================================================
# Row 2 — 5:5  최저임금 5년 | CPI·PPI
# =============================================================================
row2_left, row2_right = st.columns([5, 5], gap="small")

with row2_left:
    render_section_title("💰 최저임금 5년 추이 (시간당 Gross)")
    if wage_trend and wage_trend.get("figure") is not None:
        fig_wage = apply_report_chart_size(wage_trend["figure"])
        st.plotly_chart(fig_wage, width="stretch", config={"displayModeBar": False})
        st.caption(wage_trend.get("source", "")[:120])
    else:
        st.caption("⚠️ 최저임금 추이 차트를 준비하지 못했습니다.")

with row2_right:
    render_section_title("📈 물가 동향 CPI · PPI (YoY, 24개월)")
    inflation = (macro_bundle or {}).get("inflation") if macro_bundle else None
    if inflation and inflation.get("figure") is not None:
        m1, m2, m3 = st.columns(3)
        m1.metric("CPI YoY", f"{inflation['latest_cpi']:.1f}%")
        m2.metric("PPI YoY", f"{inflation['latest_ppi']:.1f}%")
        m3.metric("갭", f"{inflation['latest_gap']:+.1f}%p")
        fig_inf = apply_report_chart_size(inflation["figure"])
        st.plotly_chart(fig_inf, width="stretch", config={"displayModeBar": False})
        extra = " · 더미 폴백" if inflation.get("is_dummy") else ""
        st.caption(f"{inflation.get('latest_month', '')} · {inflation.get('source', '')}{extra}")
    else:
        st.caption("⚠️ CPI/PPI 차트를 준비하지 못했습니다.")


# =============================================================================
# Row 3 — 6:4  에너지/가스 | OSD
# =============================================================================
row3_left, row3_right = st.columns([6, 4], gap="small")

with row3_left:
    render_section_title("⚡ 산업용 에너지 · 가스 단가 (36개월)")
    if energy_bundle and energy_bundle.get("figure") is not None:
        fig_e = apply_report_chart_size(energy_bundle["figure"], height=280)
        st.plotly_chart(fig_e, width="stretch", config={"displayModeBar": False})
        table = energy_bundle.get("display_table")
        if table is not None and not getattr(table, "empty", True):
            st.dataframe(table, width="stretch", hide_index=True, height=220)
        note = energy_bundle.get("source", "")
        if energy_bundle.get("is_fx_fallback"):
            st.caption(f"⚠️ {note}")
        else:
            st.caption(note)
    else:
        st.caption("⚠️ 에너지/가스 단가 데이터를 준비하지 못했습니다.")

with row3_right:
    render_section_title("🏭 OSD 자동차 생산 · 수출 (12개월)")
    auto = (macro_bundle or {}).get("auto") if macro_bundle else None
    if auto and auto.get("figure") is not None:
        a1, a2, a3 = st.columns(3)
        a1.metric("생산", f"{auto['latest_production']:,}")
        a2.metric("수출", f"{auto['latest_export']:,}")
        a3.metric("YoY", f"{auto['production_yoy']:+.1f}%")
        fig_osd = apply_report_chart_size(auto["figure"])
        st.plotly_chart(fig_osd, width="stretch", config={"displayModeBar": False})
        extra = " · 더미" if auto.get("is_dummy") else ""
        st.caption(f"{auto.get('latest_month', '')} · {auto.get('source', '')}{extra}")
    else:
        st.caption("⚠️ OSD 동향을 준비하지 못했습니다.")

st.caption(
    "참고 자료이며 공식 의사결정의 대체 정보가 아닙니다. "
    "환율: yfinance · 물가: TÜİK/TCMB · 뉴스: Google News + Gemini."
)
