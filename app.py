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
# news_data.py)에 나누어 정리했습니다. 이렇게 "기능별로 파일을 나누는 것"을
# 모듈화(modularization)라고 하며, 코드가 길어져도 유지보수하기 쉬워집니다.
#
# 화면 구성 순서 (위 -> 아래):
#   1) 상단: EUR/TRY, USD/TRY, TRY/KRW 환율 카드
#   2) 터키 기준금리 (최근 2년 월별 그래프)
#   3) 터키 최저임금 + 환율 환산(EUR/USD/KRW)
#   4) 터키 현지 뉴스 (더미 데이터, 펼치면 터키어 원문 확인 가능)
# =============================================================================

import streamlit as st
import plotly.graph_objects as go

# 우리가 modules 폴더에 나누어 만든 함수들을 가져옵니다.
from modules.fx_rates import get_all_fx_rates, FX_TICKERS
from modules.policy_rate import get_policy_rate_dataframe, get_latest_policy_rate
from modules.minimum_wage import get_minimum_wage_info, convert_wage_to_foreign_currencies
from modules.news_data import get_dummy_news


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


# =============================================================================
# 헤더(맨 위 제목) 영역
# =============================================================================
st.title("🇹🇷 터키 비즈니스 & 경제 동향 대시보드")
st.caption(
    "환율 · 기준금리 · 최저임금 · 현지 뉴스를 한 화면에서 확인하세요. "
    "(환율은 yfinance 실시간 데이터, 뉴스는 레이아웃 확인용 예시 데이터입니다.)"
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

st.caption("데이터 출처: Yahoo Finance (yfinance) · 5분마다 자동 갱신")

st.divider()


# =============================================================================
# 3. 섹션 2 — 터키 기준금리 (최근 2년 월별 추이)
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
    # use_container_width=True 로 두면 화면(컨테이너) 너비에 맞춰 그래프가 자동으로 늘어나거나 줄어듭니다.
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.caption(
    "⚠️ 기준금리 데이터는 참고용 샘플 데이터입니다. 실제 서비스에서는 터키 중앙은행(TCMB)의 "
    "공개 데이터 시스템(EVDS) API 등으로 교체하는 것을 권장합니다."
)

st.divider()


# =============================================================================
# 4. 섹션 3 — 터키 최저임금 + 환율 환산
# -----------------------------------------------------------------------------
# modules/minimum_wage.py 에서 정의한 최저임금(TRY)을 위에서 이미 가져온
# 환율 데이터(fx_rates)를 이용해 EUR / USD / KRW로 환산해서 함께 보여줍니다.
# =============================================================================
render_section_title("💰 터키 최저임금 (순 수령액 기준)")

wage_info = get_minimum_wage_info()
net_wage_try = wage_info["net_wage_try"]

# 환율을 이용해 최저임금을 외화로 환산합니다.
converted = convert_wage_to_foreign_currencies(net_wage_try, fx_rates)

wage_col1, wage_col2, wage_col3, wage_col4 = st.columns(4)

with wage_col1:
    with st.container(border=True):
        st.markdown("**최저임금 (TRY)**")
        st.markdown(
            f"<div class='big-number'>₺ {format_number(net_wage_try, 0)}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"적용 기간: {wage_info['effective_period']}")

with wage_col2:
    with st.container(border=True):
        st.markdown("**≈ EUR (유로)**")
        eur_value = converted["EUR"]
        display_value = f"€ {format_number(eur_value, 0)}" if eur_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 EUR/TRY 환율 기준")

with wage_col3:
    with st.container(border=True):
        st.markdown("**≈ USD (달러)**")
        usd_value = converted["USD"]
        display_value = f"$ {format_number(usd_value, 0)}" if usd_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 USD/TRY 환율 기준")

with wage_col4:
    with st.container(border=True):
        st.markdown("**≈ KRW (원)**")
        krw_value = converted["KRW"]
        display_value = f"₩ {format_number(krw_value, 0)}" if krw_value else "-"
        st.markdown(f"<div class='big-number'>{display_value}</div>", unsafe_allow_html=True)
        st.caption("현재 TRY/KRW 환율 기준")

st.caption("⚠️ 최저임금 금액은 예시 기준 데이터이며, 최신 정부 발표 금액으로 업데이트가 필요합니다.")

st.divider()


# =============================================================================
# 5. 섹션 4 — 터키 현지 뉴스 (무역 / 관세 / 최저임금 / 노조)
# -----------------------------------------------------------------------------
# 지금은 modules/news_data.py 의 더미(임시) 데이터를 사용해서 화면 레이아웃만
# 먼저 잡아둔 상태입니다. 나중에 실제 뉴스 API/크롤러를 연결할 때는
# get_dummy_news() 함수의 반환값만 실제 데이터로 바꿔주면 됩니다.
#
# 각 뉴스는 다음과 같이 구성됩니다.
#   - 제목 + 한국어 3줄 요약 : 펼치지 않아도 바로 보이는 부분
#   - st.expander(...)      : 클릭하면 펼쳐지면서 터키어 원문이 보이는 부분
# =============================================================================
render_section_title("📰 터키 현지 뉴스 (무역 · 관세 · 최저임금 · 노조)")

news_list = get_dummy_news()

for news in news_list:
    with st.container(border=True):
        # 카테고리 배지(태그)와 발행일/출처를 한 줄에 표시
        st.markdown(
            f"<span class='news-badge'>{news['category']}</span> "
            f"<span class='small-caption'>{news['date']} · {news['source']}</span>",
            unsafe_allow_html=True,
        )

        # 한국어 제목 (굵고 크게)
        st.markdown(f"#### {news['title_kr']}")

        # 한국어 3줄 요약 — 리스트 형태의 각 문장을 불릿(•)으로 보여줍니다.
        for line in news["summary_kr"]:
            st.markdown(f"- {line}")

        # st.expander를 사용하면 기본적으로는 접혀 있다가,
        # 사용자가 클릭하면 펼쳐지면서 안의 내용(터키어 원문)이 보입니다.
        # 이렇게 하면 화면이 복잡해지지 않고, 필요한 사람만 원문을 확인할 수 있습니다.
        with st.expander("🇹🇷 터키어 원문 기사 보기 (Orijinal Türkçe Haber)"):
            st.markdown(f"**{news['title_tr']}**")
            st.write(news["content_tr"])

st.divider()

# =============================================================================
# 푸터(맨 아래 안내 문구)
# =============================================================================
st.caption(
    "본 대시보드의 환율 정보는 Yahoo Finance(yfinance) 데이터를 기반으로 하며, "
    "투자/거래 판단의 참고 자료일 뿐 공식 금융 정보로 사용할 수 없습니다. "
    "뉴스 섹션은 현재 레이아웃 확인용 예시(더미) 데이터입니다."
)
