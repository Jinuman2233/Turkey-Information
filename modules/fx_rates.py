# =============================================================================
# fx_rates.py
# -----------------------------------------------------------------------------
# 이 파일은 "환율(외환 시세)" 데이터를 야후 파이낸스(yfinance)에서 가져오는
# 역할을 담당합니다.
#
# 초보자를 위한 설명:
# - yfinance는 야후 파이낸스(Yahoo! Finance) 사이트의 데이터를 파이썬에서
#   쉽게 가져올 수 있게 해주는 라이브러리입니다.
# - 환율 티커(ticker, 종목 코드)는 보통 "통화1통화2=X" 형태로 씁니다.
#   예) "USDTRY=X"  -> 1 미국달러(USD)가 몇 터키리라(TRY)인지
#       "EURTRY=X"  -> 1 유로(EUR)가 몇 터키리라(TRY)인지
# - 만약 인터넷 연결이 안 되거나 야후 파이낸스 서버가 응답하지 않으면
#   프로그램이 죽지 않도록 예외 처리(try-except)를 꼼꼼히 해두었습니다.
# =============================================================================

import streamlit as st
import yfinance as yf
import pandas as pd


# -----------------------------------------------------------------------------
# 화면에 보여줄 환율 3종의 이름과 야후 파이낸스 티커를 미리 정의해 둡니다.
# key   : 화면/코드에서 사용할 식별자
# value : (사람이 읽기 좋은 이름, yfinance 티커, 설명)
# -----------------------------------------------------------------------------
FX_TICKERS = {
    "EURTRY": {
        "label": "EUR/TRY (유로 → 터키리라)",
        "ticker": "EURTRY=X",
    },
    "USDTRY": {
        "label": "USD/TRY (달러 → 터키리라)",
        "ticker": "USDTRY=X",
    },
    "TRYKRW": {
        "label": "TRY/KRW (터키리라 → 한국원)",
        "ticker": "TRYKRW=X",
    },
}


@st.cache_data(ttl=300, show_spinner=False)  # 5분(300초) 동안 결과를 캐시(임시 저장)해서 API 호출을 줄여줌
def _fetch_single_rate(ticker: str):
    """
    야후 파이낸스에서 특정 티커의 '현재가(최근 종가)'와
    '전일 대비 변동값/변동률'을 가져오는 내부(private) 함수입니다.

    Parameters
    ----------
    ticker : str
        예) "USDTRY=X"

    Returns
    -------
    dict 형태로 {현재가, 전일종가, 변동값, 변동률(%)} 를 반환합니다.
    데이터를 가져오지 못하면 None을 반환합니다.
    """
    try:
        # yf.Ticker(...)로 종목 객체를 만들고, 최근 5일치 일봉 데이터를 요청합니다.
        # (주말/공휴일을 감안해서 넉넉하게 5일을 요청 -> 마지막 2개 값만 사용)
        data = yf.Ticker(ticker).history(period="5d", interval="1d")

        if data is None or data.empty or "Close" not in data.columns:
            return None

        closes = data["Close"].dropna()
        if len(closes) == 0:
            return None

        current_price = float(closes.iloc[-1])

        # 전일 종가가 있으면 변동값/변동률을 계산하고, 없으면 0으로 처리합니다.
        if len(closes) >= 2:
            previous_price = float(closes.iloc[-2])
        else:
            previous_price = current_price

        change = current_price - previous_price
        change_pct = (change / previous_price * 100) if previous_price != 0 else 0.0

        return {
            "current": current_price,
            "previous": previous_price,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        # 네트워크 오류, 서버 오류 등 어떤 문제든 여기서 잡아서
        # 앱 전체가 멈추지 않도록 None을 돌려줍니다.
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_cross_rate_try_krw():
    """
    'TRYKRW=X' 티커를 야후에서 바로 지원하지 않는 경우를 대비한 대체(fallback) 함수입니다.

    계산 방법 (교차 환율, cross rate):
        1 USD = USDTRY TRY  =>  1 TRY = (1 / USDTRY) USD
        1 USD = USDKRW KRW
        따라서 1 TRY = USDKRW / USDTRY  (KRW 단위)
    즉, 미국 달러를 매개로 삼아 TRY -> KRW 환율을 간접적으로 계산합니다.
    """
    try:
        usdtry = yf.Ticker("USDTRY=X").history(period="5d", interval="1d")["Close"].dropna()
        usdkrw = yf.Ticker("USDKRW=X").history(period="5d", interval="1d")["Close"].dropna()

        if usdtry.empty or usdkrw.empty:
            return None

        current = float(usdkrw.iloc[-1]) / float(usdtry.iloc[-1])

        if len(usdtry) >= 2 and len(usdkrw) >= 2:
            previous = float(usdkrw.iloc[-2]) / float(usdtry.iloc[-2])
        else:
            previous = current

        change = current - previous
        change_pct = (change / previous * 100) if previous != 0 else 0.0

        return {
            "current": current,
            "previous": previous,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


def get_fx_rate(fx_key: str):
    """
    'EURTRY', 'USDTRY', 'TRYKRW' 중 하나를 받아서
    해당 환율 데이터를 딕셔너리로 반환하는 공개(public) 함수입니다.

    TRYKRW의 경우, 야후에서 직접 값을 못 가져오면
    USD를 매개로 한 교차 환율 계산으로 자동 대체합니다.
    """
    info = FX_TICKERS[fx_key]
    result = _fetch_single_rate(info["ticker"])

    # TRYKRW=X 티커가 야후에서 지원되지 않거나 값이 비어 있는 경우 -> 교차 환율로 재계산
    if result is None and fx_key == "TRYKRW":
        result = _fetch_cross_rate_try_krw()

    return result


def get_all_fx_rates():
    """
    EUR/TRY, USD/TRY, TRY/KRW 세 가지 환율을 한 번에 딕셔너리로 모아서 반환합니다.
    화면(app.py)에서는 이 함수 하나만 호출하면 됩니다.
    """
    return {key: get_fx_rate(key) for key in FX_TICKERS.keys()}
