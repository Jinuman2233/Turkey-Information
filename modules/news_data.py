# =============================================================================
# news_data.py
# -----------------------------------------------------------------------------
# 이 파일은 "터키 현지 뉴스" 섹션에 사용할 더미(임시) 데이터를 관리합니다.
#
# 초보자를 위한 설명:
# - 아직 실제 뉴스 API(예: 네이버 뉴스 API, NewsAPI, 언론사 크롤링 등)를
#   연결하기 전이므로, 화면 레이아웃(디자인)을 먼저 잡기 위한 '가짜 데이터'를
#   이 파일에 미리 만들어 둡니다.
# - 나중에 실제 뉴스 데이터를 연결할 때는, 아래 리스트(DUMMY_NEWS)와
#   똑같은 형태(제목/요약/원문 등의 key)로 데이터를 채워주면
#   app.py 코드를 거의 수정하지 않고도 바로 실제 뉴스로 교체할 수 있습니다.
#
# 각 뉴스 데이터는 아래와 같은 항목(key)을 가진 딕셔너리입니다.
#   - category      : 뉴스 분류 (무역 / 관세 / 최저임금 / 노조 등)
#   - title_kr      : 한국어 제목
#   - summary_kr    : 한국어 3줄 요약 (리스트 형태, 각 항목이 한 줄)
#   - title_tr      : 터키어 원문 제목 (예시)
#   - content_tr    : 터키어 원문 기사 내용 (예시, 더미 텍스트)
#   - source        : 출처 (예시)
#   - date          : 발행일 (예시)
#   - link          : 원문 기사 링크 (예시 데이터라 실제 기사는 없으므로, 터키어 제목으로
#                     검색되는 구글 검색 링크를 대신 넣어 둡니다)
#
# ※ modules/news_crawler.py(실시간 AI 번역 뉴스)에서 반환하는 뉴스 데이터도
#   동일한 key(category, title_kr, summary_kr, link, source, date)를 사용하도록
#   맞춰 두었습니다. 그래서 app.py의 화면을 그리는 코드는 두 데이터 소스 중
#   어떤 것을 받아도 수정 없이 그대로 동작합니다.
# =============================================================================

from urllib.parse import quote_plus


DUMMY_NEWS = [
    {
        "category": "관세",
        "title_kr": "터키, EU와 관세동맹 현대화 협상 재개",
        "summary_kr": [
            "터키와 EU가 1995년 체결된 관세동맹 협정의 현대화 협상을 다시 시작했습니다.",
            "농산물, 서비스, 공공조달 분야까지 관세동맹 범위를 넓히는 것이 핵심 의제입니다.",
            "터키 정부는 이번 협상이 타결되면 對EU 수출 기업들의 비용 부담이 줄어들 것으로 기대하고 있습니다.",
        ],
        "title_tr": "Türkiye, AB ile Gümrük Birliği'nin Güncellenmesi İçin Müzakerelere Yeniden Başladı",
        "content_tr": (
            "Türkiye ile Avrupa Birliği (AB) arasında 1995 yılında imzalanan Gümrük Birliği "
            "Anlaşması'nın güncellenmesine ilişkin müzakereler yeniden başladı. Ticaret Bakanlığı "
            "yetkilileri, görüşmelerin öncelikli olarak tarım ürünleri, hizmetler ve kamu alımları "
            "gibi alanları kapsayacak şekilde genişletilmesini hedeflediklerini açıkladı.\n\n"
            "Yetkililer, anlaşmanın güncellenmesi durumunda Türk ihracatçıların AB pazarına erişiminin "
            "kolaylaşacağını ve gümrük prosedürlerinde önemli maliyet avantajları sağlanacağını "
            "belirtti. Sanayi kuruluşları ise sürecin hızlandırılmasını talep ediyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 통신사 (Örnek Haber Ajansı)",
        "date": "2026-07-20",
    },
    {
        "category": "최저임금",
        "title_kr": "터키 노동부, 2026년 하반기 최저임금 재조정 검토 착수",
        "summary_kr": [
            "터키 노동사회보장부가 높은 물가 상승률을 반영해 최저임금 재조정 논의를 시작했습니다.",
            "노동자 측은 실질임금 하락을 막기 위한 인상률 상향을 요구하고 있습니다.",
            "경영자 단체는 급격한 인상이 중소기업 고용에 부담이 될 수 있다고 우려를 표하고 있습니다.",
        ],
        "title_tr": "Çalışma Bakanlığı, 2026 Yılının İkinci Yarısı İçin Asgari Ücret Güncellemesini Değerlendiriyor",
        "content_tr": (
            "Çalışma ve Sosyal Güvenlik Bakanlığı, yüksek enflasyon oranlarını dikkate alarak "
            "asgari ücretin yıl içinde yeniden değerlendirilmesi konusundaki çalışmalara başladı. "
            "İşçi sendikaları, reel ücret kaybının önlenmesi için ücret artış oranının yükseltilmesini "
            "talep ediyor.\n\n"
            "İşveren kuruluşları ise ani ve yüksek oranlı bir artışın özellikle küçük ve orta ölçekli "
            "işletmelerin istihdam kapasitesine olumsuz etki edebileceğini belirtiyor. Asgari Ücret "
            "Tespit Komisyonu'nun konuyla ilgili toplantı takvimini yakında açıklaması bekleniyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 경제신문 (Örnek Ekonomi Gazetesi)",
        "date": "2026-07-18",
    },
    {
        "category": "노조",
        "title_kr": "터키 최대 노총, 임금 인상 요구하며 총파업 예고",
        "summary_kr": [
            "터키 최대 노동조합 연맹이 물가 상승에 못 미치는 임금 인상에 반발해 총파업을 예고했습니다.",
            "제조업, 물류, 항만 등 주요 산업 분야 노동자들이 파업에 동참할 것으로 알려졌습니다.",
            "정부와 노조는 파업을 막기 위한 추가 협상을 이어가고 있으나 아직 합의에 이르지 못했습니다.",
        ],
        "title_tr": "Türkiye'nin En Büyük İşçi Sendikası Konfederasyonu Genel Grev Uyarısında Bulundu",
        "content_tr": (
            "Türkiye'nin en büyük işçi sendikaları konfederasyonu, enflasyonun altında kalan ücret "
            "artışlarına tepki olarak genel grev çağrısında bulundu. Sendika yetkilileri, imalat, "
            "lojistik ve liman işletmeciliği gibi kritik sektörlerdeki işçilerin greve destek "
            "vereceğini duyurdu.\n\n"
            "Hükümet ile sendikalar arasında grevi önlemeye yönelik ek görüşmeler sürdürülüyor, "
            "ancak taraflar arasında henüz bir uzlaşmaya varılamadı. Uzmanlar, olası bir grevin "
            "tedarik zincirinde kısa süreli aksaklıklara yol açabileceğini belirtiyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 노동뉴스 (Örnek Emek Haber)",
        "date": "2026-07-15",
    },
    {
        "category": "무역",
        "title_kr": "터키, 중앙아시아 국가들과 자유무역협정 확대 추진",
        "summary_kr": [
            "터키 정부가 우즈베키스탄, 카자흐스탄 등 중앙아시아 국가들과의 FTA 확대를 추진하고 있습니다.",
            "튀르크어권 국가 간 경제협력체 '튀르크 국가기구(OTS)'를 통한 교역 활성화가 목표입니다.",
            "관련 업계는 관세 인하와 통관 절차 간소화로 물류 비용이 낮아질 것으로 기대하고 있습니다.",
        ],
        "title_tr": "Türkiye, Orta Asya Ülkeleriyle Serbest Ticaret Anlaşmalarını Genişletmeyi Planlıyor",
        "content_tr": (
            "Ticaret Bakanlığı, Özbekistan ve Kazakistan başta olmak üzere Orta Asya ülkeleriyle "
            "serbest ticaret anlaşmalarının kapsamının genişletilmesi için çalışmalar yürütüyor. "
            "Türk Devletleri Teşkilatı (TDT) çatısı altında bölgesel ticaretin canlandırılması "
            "hedefleniyor.\n\n"
            "Sektör temsilcileri, gümrük tarifelerinin düşürülmesi ve gümrükleme süreçlerinin "
            "basitleştirilmesi sayesinde lojistik maliyetlerinin önemli ölçüde azalacağını "
            "öngörüyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 무역저널 (Örnek Ticaret Dergisi)",
        "date": "2026-07-10",
    },
    {
        "category": "관세",
        "title_kr": "미국, 터키산 철강에 대한 추가 관세 부과 검토",
        "summary_kr": [
            "미국 상무부가 터키산 철강 제품에 대한 반덤핑 관세 부과 여부를 재검토하고 있습니다.",
            "터키 철강업계는 자국 제품이 부당하게 표적이 되고 있다며 강하게 반발하고 있습니다.",
            "이번 조치가 확정되면 터키의 대미 철강 수출에 상당한 타격이 예상됩니다.",
        ],
        "title_tr": "ABD, Türk Çeliğine Ek Gümrük Tarifesi Uygulamayı Değerlendiriyor",
        "content_tr": (
            "ABD Ticaret Bakanlığı, Türkiye menşeli çelik ürünlerine yönelik anti-damping "
            "vergisi uygulanıp uygulanmayacağını yeniden değerlendirmeye aldı. Türk çelik sektörü "
            "temsilcileri, ürünlerinin haksız yere hedef gösterildiğini savunarak karara sert "
            "tepki gösterdi.\n\n"
            "Sektör uzmanları, olası bir ek tarifenin Türkiye'nin ABD'ye yönelik çelik "
            "ihracatını ciddi şekilde olumsuz etkileyebileceğini belirtiyor. Türk hükümetinin "
            "konuyla ilgili diplomatik girişimlerde bulunacağı bildiriliyor.\n\n"
            "(※ 이 기사는 화면 레이아웃 확인을 위한 예시 더미 텍스트입니다.)"
        ),
        "source": "예시 국제경제뉴스 (Örnek Uluslararası Ekonomi Haberleri)",
        "date": "2026-07-05",
    },
]


# 더미 데이터에는 실제 기사 링크가 없으므로, 터키어 제목으로 검색되는
# 구글 검색 링크를 만들어서 "링크가 항상 동작하는" 예시로 사용합니다.
for _news_item in DUMMY_NEWS:
    _news_item["link"] = f"https://www.google.com/search?q={quote_plus(_news_item['title_tr'])}"


def get_dummy_news() -> list:
    """
    더미(임시) 뉴스 데이터 리스트를 반환합니다.
    실제 뉴스 API로 교체할 때는 이 함수의 반환값만
    동일한 구조(list of dict)로 바꿔주면 됩니다.
    """
    return DUMMY_NEWS
