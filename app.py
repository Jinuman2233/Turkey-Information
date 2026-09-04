# =============================================================================
# app.py
# -----------------------------------------------------------------------------
# 터키 비즈니스 & 경제 동향 — 모니터 1화면(스크롤 없음) 고밀도 그리드.
# 데이터 로직은 modules/ 에 두고, 이 파일은 배치·높이만 담당합니다.
#
# Top    (3:7)  환율·기준금리 KPI | 뉴스 (내부 스크롤)
# Middle (1:1)  최저임금 차트     | CPI·PPI 차트
# Bottom (6:4)  에너지 차트+표    | OSD 요약+차트
# =============================================================================

import html

import streamlit as st

from modules.fx_rates import get_all_fx_rates, FX_TICKERS
from modules.policy_rate import get_latest_policy_rate
from modules.minimum_wage import get_hourly_gross_wage_trend, MONTHLY_WORKING_HOURS
from modules.energy_data import get_energy_price_bundle
from modules.macro_industry import get_macro_industry_bundle, render_osd_industry_section
from modules.news_data import get_dummy_news
from modules.news_crawler import (
    API_QUOTA_FALLBACK_MESSAGE,
    fetch_ai_translated_news,
    filter_display_news_recent,
    is_ai_translation_configured,
)

NEWS_DISPLAY_LIMIT = 5
CHART_HEIGHT = 180
BOTTOM_CHART_HEIGHT = 150
TABLE_HEIGHT = 150
CHART_MARGIN = dict(t=18, b=6, l=8, r=8)

st.set_page_config(
    page_title="터키 비즈니스 & 경제 동향 대시보드",
    page_icon="🇹🇷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"],
        [data-testid="stMain"], section.main, .stApp, .main {
            height: 100vh !important;
            max-height: 100vh !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }
        .block-container, [data-testid="stMainBlockContainer"] {
            padding-top: 0.35rem !important;
            padding-bottom: 0 !important;
            padding-left: 0.7rem !important;
            padding-right: 0.7rem !important;
            max-width: 100% !important;
            height: 100vh !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }
        header[data-testid="stHeader"], div[data-testid="stToolbar"],
        #MainMenu, footer, [data-testid="stDecoration"],
        .stDeployButton, [data-testid="stStatusWidget"] { display: none !important; }

        h1, h2, h3 { margin: 0 !important; padding: 0 !important; font-size: 1.02rem !important; line-height: 1.2 !important; }
        .stCaption, [data-testid="stCaptionContainer"] { display: none !important; }
        .stMarkdown, .stMarkdown p { margin: 0 !important; padding: 0 !important; }

        div[data-testid="stVerticalBlock"] { gap: 0.12rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.35rem !important; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { padding: 0 0.1rem !important; }
        .stElementContainer, .element-container, [data-testid="stElementContainer"] {
            margin: 0 !important; padding: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] { padding: 0 !important; }

        [data-testid="stPlotlyChart"] {
            margin: 0 !important;
            padding: 0 !important;
        }
        [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.7rem !important; }
        [data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
            height: 21vh !important;
            min-height: 130px;
        }

        .page-title {
            font-size: 0.98rem; font-weight: 800; line-height: 1.2;
            margin: 0 0 0.15rem 0; color: #1a1a1a;
        }
        .section-title {
            font-size: 0.78rem; font-weight: 700; margin: 0 0 0.08rem 0;
            border-left: 3px solid #C8102E; padding-left: 0.35rem; line-height: 1.2;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .kpi-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: 0.28rem;
        }
        .kpi {
            background: #f4f5f6; border-radius: 6px; padding: 0.28rem 0.42rem;
        }
        .kpi-l { font-size: 0.68rem; color: #666; line-height: 1.1; }
        .kpi-v { font-size: 1.05rem; font-weight: 800; line-height: 1.15; }
        .kpi-d { font-size: 0.7rem; font-weight: 600; }
        .kpi-d.up { color: #C8102E; }
        .kpi-d.down { color: #1565C0; }
        .kpi-d.flat { color: #6b6b6b; }
        .mini-stats { font-size: 0.72rem; color: #444; margin: 0 0 0.05rem 0; }
        .mini-stats b { font-weight: 700; }

        .news-scroll-box {
            height: 18vh; min-height: 110px; max-height: 180px;
            overflow-y: auto; border: 1px solid #e6e6e6;
            border-radius: 6px; padding: 0.2rem 0.5rem; background: #fff;
        }
        .news-item { padding: 0.18rem 0; border-bottom: 1px solid #eee; }
        .news-item:last-child { border-bottom: none; }
        .news-title {
            font-weight: 700; font-size: 0.78rem; line-height: 1.25;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .news-meta { font-size: 0.68rem; color: #6b6b6b; }
        .news-badge {
            display: inline-block; background-color: #C8102E; color: white;
            font-size: 0.62rem; font-weight: 600; padding: 0 6px;
            border-radius: 999px; margin-right: 5px;
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
    st.markdown(f"<div class='section-title'>{html.escape(text)}</div>", unsafe_allow_html=True)


def apply_chart_size(fig, height: int = CHART_HEIGHT):
    if fig is None:
        return None
    fig.update_layout(
        height=height,
        margin=CHART_MARGIN,
        autosize=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            font=dict(size=9),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def render_kpi_grid(cards: list) -> None:
    cells = []
    for card in cards:
        delta = card.get("delta") or 0
        if delta > 0:
            cls = "up"
        elif delta < 0:
            cls = "down"
        else:
            cls = "flat"
        cells.append(
            "<div class='kpi'>"
            f"<div class='kpi-l'>{html.escape(card['label'])}</div>"
            f"<div class='kpi-v'>{html.escape(card['value'])}</div>"
            f"<div class='kpi-d {cls}'>{html.escape(card['delta_text'])}</div>"
            "</div>"
        )
    st.markdown(f"<div class='kpi-grid'>{''.join(cells)}</div>", unsafe_allow_html=True)


def render_news_scroll_box(news_list: list) -> None:
    items = []
    for news in news_list:
        title = html.escape(str(news.get("title_kr") or "(제목 없음)"))
        category = html.escape(str(news.get("category") or ""))
        date = html.escape(str(news.get("date") or "날짜 미상"))
        source = html.escape(str(news.get("source") or ""))
        raw_link = str(news.get("link") or "").strip()
        if raw_link.startswith("http://") or raw_link.startswith("https://"):
            href = html.escape(raw_link, quote=True)
            link_html = f' · <a href="{href}" target="_blank" rel="noopener">원문</a>'
        else:
            link_html = ""
        items.append(
            "<div class='news-item'>"
            f"<div class='news-title' title='{title}'>{title}</div>"
            f"<div class='news-meta'><span class='news-badge'>{category}</span>"
            f"{date} · {source}{link_html}</div>"
            "</div>"
        )
    st.markdown(
        f'<div class="news-scroll-box">{"".join(items) or "표시할 뉴스가 없습니다."}</div>',
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
    news_mode = news_result.get("news_mode") or ("live" if news_list else "empty")
    news_list = filter_display_news_recent(news_list)
    if not news_list:
        return get_dummy_news()[:NEWS_DISPLAY_LIMIT], news_mode, True
    return news_list[:NEWS_DISPLAY_LIMIT], news_mode, False


st.markdown("<div class='page-title'>🇹🇷 터키 비즈니스 & 경제 동향</div>", unsafe_allow_html=True)

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
    news_list, _, _ = load_news_list()


# Top — 3:7
col1, col2 = st.columns([3, 7], gap="small")

with col1:
    render_section_title("💱 환율 · 🏦 기준금리")
    kpi_cards = []
    for fx_key, info in FX_TICKERS.items():
        rate = fx_rates.get(fx_key)
        short_label = info["label"].split("(")[0].strip()
        if rate is None:
            kpi_cards.append({"label": short_label, "value": "-", "delta_text": "-", "delta": 0})
        else:
            kpi_cards.append(
                {
                    "label": short_label,
                    "value": format_number(rate["current"]),
                    "delta_text": f"{rate['change_pct']:+.2f}%",
                    "delta": rate["change"],
                }
            )
    change = latest_rate_info.get("change") or 0
    change_text = f"{change:+.2f}%p" if change != 0 else "변동 없음"
    kpi_cards.append(
        {
            "label": "기준금리 (1주 레포)",
            "value": f"{latest_rate_info['rate']:.2f}%",
            "delta_text": f"{latest_rate_info['month']} · {change_text}",
            "delta": change,
        }
    )
    render_kpi_grid(kpi_cards)

with col2:
    render_section_title("📰 터키 실시간 AI 번역 뉴스")
    render_news_scroll_box(news_list)


# Middle — 1:1
col3, col4 = st.columns(2, gap="small")

with col3:
    render_section_title("💰 최저임금 5년 추이 (시간당 Gross)")
    if wage_trend and wage_trend.get("figure") is not None:
        st.plotly_chart(
            apply_chart_size(wage_trend["figure"], CHART_HEIGHT),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )

with col4:
    inflation = (macro_bundle or {}).get("inflation") if macro_bundle else None
    if inflation and inflation.get("figure") is not None:
        render_section_title(
            f"📈 CPI {inflation['latest_cpi']:.1f}% · PPI {inflation['latest_ppi']:.1f}% · "
            f"갭 {inflation['latest_gap']:+.1f}%p"
        )
        st.plotly_chart(
            apply_chart_size(inflation["figure"], CHART_HEIGHT),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )
    else:
        render_section_title("📈 물가 동향 CPI · PPI")


# Bottom — 6:4
col5, col6 = st.columns([6, 4], gap="small")

with col5:
    render_section_title("⚡ 산업용 에너지 · 가스 단가")
    if energy_bundle:
        energy_left, energy_right = st.columns([5, 5], gap="small")
        with energy_left:
            if energy_bundle.get("figure") is not None:
                st.plotly_chart(
                    apply_chart_size(energy_bundle["figure"], BOTTOM_CHART_HEIGHT),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                )
        with energy_right:
            table = energy_bundle.get("display_table")
            if table is not None and not getattr(table, "empty", True):
                st.dataframe(table, width="stretch", hide_index=True, height=TABLE_HEIGHT)

with col6:
    auto = (macro_bundle or {}).get("auto") if macro_bundle else None
    render_osd_industry_section(auto)
