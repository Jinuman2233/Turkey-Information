# =============================================================================
# policy_rate.py
# -----------------------------------------------------------------------------
# 이 파일은 "터키 기준금리(정책금리)"의 월별 데이터를 관리합니다.
#
# 초보자를 위한 설명:
# - 터키의 기준금리는 터키 중앙은행(TCMB, Türkiye Cumhuriyet Merkez Bankası)이
#   발표하는 '1주일물 레포(repo) 금리'를 의미합니다.
# - 이 데이터는 yfinance 같은 주식/환율 라이브러리로는 가져올 수 없는
#   '중앙은행 통계' 데이터이기 때문에, 아래처럼 미리 정리해 둔 값을
#   사용합니다(=샘플/참고용 데이터).
# - 실제 서비스로 운영한다면, 터키 중앙은행의 공개 데이터 시스템인
#   EVDS(Elektronik Veri Dağıtım Sistemi, https://evds2.tcmb.gov.tr) API를
#   호출해서 이 부분을 실시간 데이터로 교체하는 것을 추천합니다.
# =============================================================================

import pandas as pd


# -----------------------------------------------------------------------------
# 월별 터키 기준금리(1주일물 레포금리, 단위: %) 샘플 데이터
# - key   : "YYYY-MM" 형식의 연-월
# - value : 해당 월의 기준금리 (%)
#
# ※ 참고용 데이터입니다. 실제 서비스에서는 TCMB(터키 중앙은행) 공식 통계로
#    교체해서 사용해 주세요.
# -----------------------------------------------------------------------------
POLICY_RATE_HISTORY = {
    "2023-08": 25.00,
    "2023-09": 30.00,
    "2023-10": 35.00,
    "2023-11": 40.00,
    "2023-12": 42.50,
    "2024-01": 45.00,
    "2024-02": 45.00,
    "2024-03": 50.00,
    "2024-04": 50.00,
    "2024-05": 50.00,
    "2024-06": 50.00,
    "2024-07": 50.00,
    "2024-08": 50.00,
    "2024-09": 50.00,
    "2024-10": 50.00,
    "2024-11": 50.00,
    "2024-12": 47.50,
    "2025-01": 45.00,
    "2025-02": 42.50,
    "2025-03": 46.00,
    "2025-04": 46.00,
    "2025-05": 46.00,
    "2025-06": 46.00,
    "2025-07": 43.00,
}


def get_policy_rate_dataframe(months: int = 24) -> pd.DataFrame:
    """
    최근 N개월(기본값 24개월 = 2년)치 터키 기준금리 데이터를
    pandas DataFrame(표 형태 데이터)으로 만들어서 반환합니다.

    Parameters
    ----------
    months : int
        가져올 개월 수 (기본 24개월 = 최근 2년)

    Returns
    -------
    pd.DataFrame
        columns = ["연월", "기준금리(%)"]
    """
    # 1) dict를 (연월, 금리) 튜플 리스트로 바꾸고, 연월 순서대로 정렬합니다.
    sorted_items = sorted(POLICY_RATE_HISTORY.items(), key=lambda x: x[0])

    # 2) 가장 최근 N개월만 잘라냅니다 (리스트의 뒤에서 N개).
    recent_items = sorted_items[-months:]

    # 3) DataFrame으로 변환합니다.
    df = pd.DataFrame(recent_items, columns=["연월", "기준금리(%)"])

    # 4) 그래프에서 날짜 순서로 잘 표시되도록 '연월'을 datetime 형식으로도 만들어 둡니다.
    df["날짜"] = pd.to_datetime(df["연월"], format="%Y-%m")

    return df


def get_latest_policy_rate() -> dict:
    """
    가장 최근 달의 기준금리와 그 직전 달의 기준금리를 반환합니다.
    (화면 상단에 "현재 몇 %, 전월 대비 몇 %p 변화"를 보여줄 때 사용)
    """
    sorted_items = sorted(POLICY_RATE_HISTORY.items(), key=lambda x: x[0])

    latest_month, latest_rate = sorted_items[-1]
    if len(sorted_items) >= 2:
        _, previous_rate = sorted_items[-2]
    else:
        previous_rate = latest_rate

    return {
        "month": latest_month,
        "rate": latest_rate,
        "previous_rate": previous_rate,
        "change": latest_rate - previous_rate,
    }
