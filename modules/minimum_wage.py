# =============================================================================
# minimum_wage.py
# -----------------------------------------------------------------------------
# 이 파일은 "터키 최저임금" 정보를 관리합니다.
#
# 초보자를 위한 설명:
# - 터키의 최저임금은 터키 정부(노동부 산하 최저임금위원회)가 발표하며,
#   보통 '순(net) 최저임금'과 '총(gross) 최저임금' 두 가지로 나뉩니다.
#   - 총(gross) 임금: 세금/보험료를 떼기 전 금액
#   - 순(net) 임금  : 근로자가 실제로 받는 금액 (세금/보험료 차감 후)
# - 이 값 역시 실시간으로 바뀌는 데이터가 아니라, 정부가 보통 1년에 1~2번
#   발표하는 값이기 때문에 아래처럼 상수(고정값)로 관리합니다.
# - 실제 서비스라면 이 값을 최신 발표 금액으로 주기적으로 업데이트해야 합니다.
# =============================================================================


# -----------------------------------------------------------------------------
# 터키 최저임금 (단위: TRY, 터키리라)
# ※ 아래 금액은 예시 기준 데이터입니다. 최신 정부 발표 금액으로 갱신해 주세요.
# -----------------------------------------------------------------------------
MINIMUM_WAGE_INFO = {
    "effective_period": "2025년 1월 ~ (발표 기준)",  # 해당 금액이 적용되는 기간
    "net_wage_try": 22_104.0,   # 순(net) 최저임금 (실수령액, TRY)
    "gross_wage_try": 26_005.5,  # 총(gross) 최저임금 (세전, TRY)
}


def get_minimum_wage_info() -> dict:
    """
    터키 최저임금 기본 정보를 딕셔너리로 반환합니다.
    """
    return MINIMUM_WAGE_INFO


def convert_wage_to_foreign_currencies(wage_try: float, fx_rates: dict) -> dict:
    """
    TRY(터키리라) 금액을 EUR, USD, KRW로 환산합니다.

    Parameters
    ----------
    wage_try : float
        환산하고 싶은 터키리라 금액 (예: 최저임금)
    fx_rates : dict
        modules.fx_rates.get_all_fx_rates() 의 결과값
        {"EURTRY": {...}, "USDTRY": {...}, "TRYKRW": {...}}

    Returns
    -------
    dict
        {"EUR": 값 또는 None, "USD": 값 또는 None, "KRW": 값 또는 None}
    """
    result = {"EUR": None, "USD": None, "KRW": None}

    # EUR/TRY 환율은 "1유로 = 몇 리라"이므로, 리라 금액을 이 값으로 나누면 유로가 됩니다.
    eurtry = fx_rates.get("EURTRY")
    if eurtry and eurtry.get("current"):
        result["EUR"] = wage_try / eurtry["current"]

    # USD/TRY 환율도 마찬가지로 "1달러 = 몇 리라"이므로 나누면 달러가 됩니다.
    usdtry = fx_rates.get("USDTRY")
    if usdtry and usdtry.get("current"):
        result["USD"] = wage_try / usdtry["current"]

    # TRY/KRW 환율은 "1리라 = 몇 원"이므로, 리라 금액에 곱하면 원화가 됩니다.
    trykrw = fx_rates.get("TRYKRW")
    if trykrw and trykrw.get("current"):
        result["KRW"] = wage_try * trykrw["current"]

    return result
