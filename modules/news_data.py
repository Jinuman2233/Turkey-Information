# =============================================================================
# news_data.py
# -----------------------------------------------------------------------------
# 이 파일은 "터키 자동차 산업 뉴스" 섹션에 사용할 더미(임시) 데이터를 관리합니다.
#
# 실제 수집(modules/news_crawler.py)이 실패할 때만 fallback으로 사용됩니다.
# 각 항목 key: category, title_kr, summary_kr, title_tr, content_tr, source, date, link
# date는 오늘 기준 상대일(하드코딩 고정일 금지)입니다.
# =============================================================================

from datetime import datetime, timedelta
from urllib.parse import quote_plus


def _relative_date(days_ago: int) -> str:
    """오늘 기준으로 N일 전 날짜를 YYYY-MM-DD로 반환합니다 (하드코딩 날짜 금지)."""
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


DUMMY_NEWS = [
    {
        "category": "자동차 산업",
        "title_kr": "터키 자동차 산업, 상반기 생산·수출 동향 점검",
        "summary_kr": [
            "터키 자동차 제조업체 협회(OSD)가 최근 생산·수출 실적을 발표했습니다.",
            "주요 완성차·부품 업체들의 가동률이 수출 수요에 연동해 움직이고 있습니다.",
            "업계는 유럽 수요와 내수 회복 속도가 하반기 실적의 핵심이라고 보고 있습니다.",
        ],
        "title_tr": "Türkiye otomotiv sanayiinde üretim ve ihracat görünümü",
        "content_tr": (
            "Otomotiv Sanayii Derneği (OSD), Türkiye otomotiv sanayiinin son dönem "
            "üretim ve ihracat performansına ilişkin değerlendirmelerde bulundu.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 자동차뉴스 (Örnek Otomotiv Haber)",
        "date": _relative_date(2),
    },
    {
        "category": "자동차 수출",
        "title_kr": "터키 자동차 수출, 유럽 시장 중심으로 회복세",
        "summary_kr": [
            "otomobil ihracatı가 유럽 주요국 수요 회복에 힘입어 증가세를 보였습니다.",
            "완성차와 부품(yan sanayi) 모두 수출 물량이 늘어난 것으로 파악됩니다.",
            "환율·물류비 변동이 수출 마진에 미치는 영향도 함께 주목받고 있습니다.",
        ],
        "title_tr": "Otomobil ihracatında Avrupa talebiyle toparlanma sinyalleri",
        "content_tr": (
            "Türkiye'nin otomobil ihracatı, Avrupa pazarındaki talep toparlanmasıyla "
            "birlikte artış eğilimi gösterdi.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 수출저널 (Örnek İhracat Dergisi)",
        "date": _relative_date(5),
    },
    {
        "category": "차량 생산",
        "title_kr": "터키 공장들의 차량 생산 계획, 하반기 가동률 상향",
        "summary_kr": [
            "주요 완성차 공장들이 araç üretimi 일정을 조정하며 가동률을 높이고 있습니다.",
            "부품 공급망 안정화가 생산 확대의 전제 조건으로 꼽힙니다.",
            "노무·물류 여건도 생산 계획에 변수로 작용하고 있습니다.",
        ],
        "title_tr": "Araç üretiminde ikinci yarı kapasite artışı planları",
        "content_tr": (
            "Türkiye'deki otomotiv üreticileri, araç üretimi planlarını güncelleyerek "
            "ikinci yarıda kapasite kullanımını artırmayı hedefliyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 제조업뉴스 (Örnek Üretim Haber)",
        "date": _relative_date(9),
    },
    {
        "category": "TOGG·전기차",
        "title_kr": "TOGG, 국내 전기차 시장 확대와 신모델 전략 발표",
        "summary_kr": [
            "터키 전기차 브랜드 TOGG가 국내 판매·충전 인프라 확장 계획을 공유했습니다.",
            "전기차 보조금·세제 정책 변화가 수요에 영향을 줄 수 있다는 분석이 나옵니다.",
            "부품 현지화와 수출 가능성에 대한 업계 관심도 커지고 있습니다.",
        ],
        "title_tr": "TOGG'dan elektrikli araç pazarı ve yeni model stratejisi",
        "content_tr": (
            "Türkiye'nin yerli elektrikli otomobil üreticisi TOGG, iç pazar büyümesi ve "
            "yeni model stratejisine ilişkin açıklamalarda bulundu.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 EV뉴스 (Örnek Elektrikli Araç Haber)",
        "date": _relative_date(14),
    },
    {
        "category": "자동차 부품·투자",
        "title_kr": "터키 자동차 부품 산업, 신규 투자·공장 증설 논의 활발",
        "summary_kr": [
            "yan sanayi 업체들이 전기차 부품 전환 투자에 속도를 내고 있습니다.",
            "외국인 투자와 현지 합작이 부품 공급망 재편에 영향을 주고 있습니다.",
            "완성차 수출 확대가 부품 수요를 함께 끌어올리는 구조입니다.",
        ],
        "title_tr": "Otomotiv yan sanayinde yatırım ve kapasite genişletme hamleleri",
        "content_tr": (
            "Otomotiv yan sanayi firmaları, elektrikli araç bileşenlerine yönelik "
            "yatırım ve fabrika kapasitesi artırımı planlarını hızlandırıyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 산업뉴스 (Örnek Sanayi Haber)",
        "date": _relative_date(21),
    },
]


for _news_item in DUMMY_NEWS:
    _news_item["link"] = f"https://www.google.com/search?q={quote_plus(_news_item['title_tr'])}"


def get_dummy_news() -> list:
    """
    더미(임시) 뉴스 데이터 리스트를 반환합니다.
    발행일은 호출 시점 기준 상대일로 다시 채워 최근 30일 이내를 유지합니다.
    """
    refreshed = []
    day_offsets = (2, 5, 9, 14, 21)
    for item, days_ago in zip(DUMMY_NEWS, day_offsets):
        copy = dict(item)
        copy["date"] = _relative_date(days_ago)
        refreshed.append(copy)
    return refreshed
