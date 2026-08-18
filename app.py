# =============================================================================
# app.py
# -----------------------------------------------------------------------------
# 터키 비즈니스 & 경제 동향 대시보드 — 고밀도 1페이지 와이드 그리드.
# 데이터 로직은 modules/ 에 두고, 이 파일은 배치·높이만 담당합니다.
#
# Top    (3:7)  환율·기준금리 metric | 뉴스 280px 스크롤 박스
# Middle (1:1)  최저임금 260px       | CPI·PPI 260px
# Bottom (6:4)  에너지 표 200px      | OSD 요약 + 차트 200px
# =============================================================================

import html

import streamlit as st

from modules.fx_rates import get_all_fx_rates, FX_TICKERS
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
CHART_HEIGHT = 260
OSD_CHART_HEIGHT = 200
ENERGY_CHART_HEIGHT = 200
TABLE_HEIGHT = 200
NEWS_BOX_HEIGHT = 280
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
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        div[data-testid="stMetricValue"] { font-size: 1.5rem; } /* 핵심 지표 폰트 크기 축소 */
        h1, h2, h3 { margin-top: 0; padding-top: 0; }

        html, body, [data-testid="stAppViewContainer"] { overflow-x: hidden; }
        header[data-testid="stHeader"] { display: none; }
        div[data-testid="stToolbar"], #MainMenu, footer { display: none !important; }
        h1, h2, h3 { margin-bottom: 0.15rem !important; font-size: 1.15rem !important; }
        .stCaption, [data-testid="stCaptionContainer"] {
            margin-top: 0 !important; margin-bottom: 0.1rem !important; font-size: 0.72rem !important;
        }
        div[data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.4rem !important; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { padding: 0 0.12rem !important; }
        .stPlotlyChart { margin: 0 !important; padding: 0 !important; }
        [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
        [data-testid="stMetric"] { background: #f7f7f8; padding: 0.35rem 0.5rem; border-radius: 6px; }
        .section-title {
            font-size: 0.88rem; font-weight: 700; margin: 0 0 0.15rem 0;
            border-left: 4px solid #C8102E; padding-left: 0.4rem; line-height: 1.2;
        }
        .news-scroll-box {
            max-height: 280px; overflow-y: auto; border: 1px solid #e6e6e6;
            border-radius: 8px; padding: 0.4rem 0.65rem; background: #fff;
        }
        .news-item { padding: 0.35rem 0; border-bottom: 1px solid #eee; }
        .news-item:last-child { border-bottom: none; }
        .news-title { font-weight: 700; font-size: 0.86rem; line-height: 1.3; margin-bottom: 0.1rem; }
        .news-meta { font-size: 0.72rem; color: #6b6b6b; margin-bottom: 0.15rem; }
        .news-item ul { margin: 0.1rem 0 0 1.1rem; padding: 0; font-size: 0.78rem; line-height: 1.3; }
        .news-badge {
            display: inline-block; background-color: #C8102E; color: white;
            font-size: 0.65rem; font-weight: 600; padding: 1px 7px;
            border-radius: 999px; margin-right: 6px;
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


def apply_chart_size(fig, height: int = CHART_HEIGHT):
    """모듈 Figure 데이터는 유지하고, 1페이지용 높이·여백만 맞춥니다."""
    if fig is None:
        return None
    fig.update_layout(height=height, margin=CHART_MARGIN, autosize=True)
    return fig


def render_news_scroll_box(news_list: list) -> None:
    """뉴스를 max-height:280px overflow-y:auto 박스 안에 가둡니다."""
    items = []
    for news in news_list:
        title = html.escape(str(news.get("title_kr") or "(제목 없음)"))
        category = html.escape(str(news.get("category") or ""))
        date = html.escape(str(news.get("date") or "날짜 미상"))
        source = html.escape(str(news.get("source") or ""))
        summaries = news.get("summary_kr") or []
        summary_html = "".join(
            f"<li>{html.escape(str(line))}</li>" for line in summaries[:2]
        )
        raw_link = str(news.get("link") or "").strip()
        if raw_link.startswith("http://") or raw_link.startswith("https://"):
            href = html.escape(raw_link, quote=True)
            link_html = f' · <a href="{href}" target="_blank" rel="noopener">원문</a>'
        else:
            link_html = ""
        items.append(
            "<div class='news-item'>"
            f"<div class='news-title'>{title}</div>"
            f"<div class='news-meta'><span class='news-badge'>{category}</span>"
            f"{date} · {source}{link_html}</div>"
            f"<ul>{summary_html}</ul>"
            "</div>"
        )
    st.markdown(
        f'<div class="news-scroll-box" style="max-height:{NEWS_BOX_HEIGHT}px; overflow-y:auto;">'
        f"{''.join(items)}</div>",
        unsafe_allow_html=True,
    )


def load_news_list() -> tuple[list, str, bool]:
    if not is_ai_translation_configured():
        return get_dummy_news()[:NEWS_DISPLAY_LIMIT], "empty", True
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
        return get_dummy_news()[:NEWS_DISPLAY_LIMIT], news_mode, True
    return news_list[:NEWS_DISPLAY_LIMIT], news_mode, False


st.markdown("### 🇹🇷 터키 비즈니스 & 경제 동향")

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
# Top Row — 3:7  환율·기준금리 | 뉴스 280px
# =============================================================================
col1, col2 = st.columns([3, 7], gap="small")

with col1:
    render_section_title("💱 환율 · 🏦 기준금리")
    fx_cols = st.columns(len(FX_TICKERS))
    for col, fx_key in zip(fx_cols, FX_TICKERS.keys()):
        info = FX_TICKERS[fx_key]
        rate = fx_rates.get(fx_key)
        short_label = info["label"].split("(")[0].strip()
        with col:
            if rate is None:
                st.metric(short_label, "-")
            else:
                st.metric(
                    short_label,
                    format_number(rate["current"]),
                    f"{rate['change_pct']:+.2f}%",
                )
    change = latest_rate_info.get("change") or 0
    change_text = f"{change:+.2f}%p" if change != 0 else "변동 없음"
    st.metric(
        "기준금리 (1주 레포)",
        f"{latest_rate_info['rate']:.2f}%",
        f"{latest_rate_info['month']} · {change_text}",
    )

with col2:
    render_section_title("📰 터키 실시간 AI 번역 뉴스")
    render_news_scroll_box(news_list)
    if is_dummy_news:
        st.caption("⚠️ 예시(더미) 뉴스")
    elif news_mode == "rss_only":
        st.caption("원문 RSS (미번역)")
    else:
        st.caption("Google News + Gemini Flash-Lite · 24시간 캐시")


# =============================================================================
# Middle Row — 1:1  최저임금 260 | CPI·PPI 260
# =============================================================================
col3, col4 = st.columns(2, gap="small")

with col3:
    render_section_title("💰 최저임금 5년 추이 (시간당 Gross)")
    if wage_trend and wage_trend.get("figure") is not None:
        fig_wage = apply_chart_size(wage_trend["figure"], height=CHART_HEIGHT)
        st.plotly_chart(fig_wage, width="stretch", config={"displayModeBar": False})
        st.caption((wage_trend.get("source") or "")[:120])
    else:
        st.caption("⚠️ 최저임금 추이 차트를 준비하지 못했습니다.")

with col4:
    render_section_title("📈 물가 동향 CPI · PPI (YoY)")
    inflation = (macro_bundle or {}).get("inflation") if macro_bundle else None
    if inflation and inflation.get("figure") is not None:
        fig_inf = apply_chart_size(inflation["figure"], height=CHART_HEIGHT)
        st.plotly_chart(fig_inf, width="stretch", config={"displayModeBar": False})
        extra = " · 더미 폴백" if inflation.get("is_dummy") else ""
        st.caption(
            f"CPI {inflation['latest_cpi']:.1f}% · PPI {inflation['latest_ppi']:.1f}% · "
            f"갭 {inflation['latest_gap']:+.1f}%p · {inflation.get('latest_month', '')}{extra}"
        )
    else:
        st.caption("⚠️ CPI/PPI 차트를 준비하지 못했습니다.")


# =============================================================================
# Bottom Row — 6:4  에너지 표+콤팩트 차트 | OSD 200
# =============================================================================
col5, col6 = st.columns([6, 4], gap="small")

with col5:
    render_section_title("⚡ 산업용 에너지 · 가스 단가")
    if energy_bundle:
        energy_left, energy_right = st.columns([5, 5], gap="small")
        with energy_left:
            if energy_bundle.get("figure") is not None:
                fig_e = apply_chart_size(energy_bundle["figure"], height=ENERGY_CHART_HEIGHT)
                st.plotly_chart(fig_e, width="stretch", config={"displayModeBar": False})
        with energy_right:
            table = energy_bundle.get("display_table")
            if table is not None and not getattr(table, "empty", True):
                st.dataframe(table, width="stretch", hide_index=True, height=TABLE_HEIGHT)
        note = energy_bundle.get("source", "")
        if energy_bundle.get("is_fx_fallback"):
            st.caption(f"⚠️ {note}")
        elif note:
            st.caption(note)
    else:
        st.caption("⚠️ 에너지/가스 단가 데이터를 준비하지 못했습니다.")

with col6:
    render_section_title("🏭 OSD 자동차 생산 · 수출")
    auto = (macro_bundle or {}).get("auto") if macro_bundle else None
    if auto and auto.get("figure") is not None:
        a1, a2, a3 = st.columns(3)
        a1.metric("생산", f"{auto['latest_production']:,}")
        a2.metric("수출", f"{auto['latest_export']:,}")
        a3.metric("YoY", f"{auto['production_yoy']:+.1f}%")
        fig_osd = apply_chart_size(auto["figure"], height=OSD_CHART_HEIGHT)
        st.plotly_chart(fig_osd, width="stretch", config={"displayModeBar": False})
        extra = " · 더미" if auto.get("is_dummy") else ""
        st.caption(f"{auto.get('latest_month', '')} · {auto.get('source', '')}{extra}")
    else:
        st.caption("⚠️ OSD 동향을 준비하지 못했습니다.")
