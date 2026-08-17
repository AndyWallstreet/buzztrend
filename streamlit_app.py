# -*- coding: utf-8 -*-
"""LK Terminal — 전체 내비게이션 (st.navigation 라우터).

실제 화면은 app_pages/ 아래 파일들이고, 이 파일은 사이드바 구조와
공통 테마(블룸버그풍 다크)만 정한다. Streamlit Cloud 의 entry point 라서
파일 이름은 streamlit_app.py 그대로 둔다.
"""
import streamlit as st

st.set_page_config(page_title="LK Terminal", page_icon="◆", layout="wide")

# ---- 블룸버그 터미널풍: 순검정 배경 + 앰버 포인트 + 대문자 섹션 라벨
st.markdown("""
<style>
/* 사이드바 — 더 검게, 경계선 한 줄 */
[data-testid="stSidebar"] {
    background: #08090b;
    border-right: 1px solid #1e2128;
}
/* 내비 섹션 제목 (Screener / Sector Watch) — 터미널 헤더처럼 */
[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {
    color: #f5a623 !important;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem !important;
    font-weight: 700;
    margin-top: 0.9rem;
}
/* 내비 링크 */
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] span {
    color: #c9ccd3;
    font-size: 0.92rem;
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover span { color: #f5a623; }
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {
    background: #15181d;
    border-left: 2px solid #f5a623;
    border-radius: 0;
}
/* 본문 배경 */
[data-testid="stAppViewContainer"] { background: #0b0d10; }
[data-testid="stHeader"] { background: #0b0d10; }
/* 지표 숫자 — 터미널처럼 등폭 숫자 */
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
h1, h2, h3 { letter-spacing: -0.01em; }
</style>
""", unsafe_allow_html=True)


def _placeholder(title, note):
    def _page():
        st.title(title)
        st.caption(note)
        st.info("준비 중입니다 — 추적 대상이 정해지면 이 자리에 대시보드가 들어옵니다.")
    _page.__name__ = "placeholder_" + "".join(ch if ch.isalnum() else "_" for ch in title)
    return _page


# ---- Screener
pg_buzz = st.Page("app_pages/buzztrend.py", title="Buzz Trend", url_path="buzz")
pg_value = st.Page("app_pages/value_screener.py", title="Value Screener",
                   url_path="밸류_스크리너")
pg_stock = st.Page("app_pages/stock_detail.py", title="Stock Picker",
                   url_path="종목상세")
pg_watch = st.Page("app_pages/watchlist.py", title="Watchlist",
                   url_path="watchlist")

# ---- Sector Watch
pg_bio = st.Page(_placeholder("Bio / Healthcare", "제약·바이오·의료기기 섹터 추적"),
                 title="Bio/Healthcare", url_path="bio-healthcare")
pg_beauty = st.Page(_placeholder("Cosmetics / Beauty", "화장품·뷰티 섹터 추적"),
                    title="Cosmetics/Beauty", url_path="cosmetics-beauty")
pg_trailer = st.Page("app_pages/hatchuping_trailer.py", title="└ 하츄핑2 예고편",
                     url_path="하츄핑2_예고편")
pg_boxoffice = st.Page("app_pages/hatchuping_boxoffice.py", title="└ 하츄핑2 개봉 후",
                       url_path="하츄핑2_개봉후")


def _entertainment():
    st.title("Entertainment / Contents")
    st.caption("엔터·콘텐츠 섹터 — 진행 중인 추적")
    st.subheader("Movie tracking", divider="orange")
    st.page_link(pg_trailer, label="1. 하츄핑2 예고편 — 유튜브 조회수·댓글, 개봉 전 예매율 기록")
    st.page_link(pg_boxoffice, label="2. 하츄핑2 개봉 후 — KOBIS 실관객수, 실관람객 평점")
    st.caption("종목: SAMG엔터 (419530) · 사랑의 하츄핑 2: 고래보석의 전설 (2026-08-05 개봉)")


pg_ent = st.Page(_entertainment, title="Entertainment/Contents", url_path="entertainment")
pg_consumer = st.Page(_placeholder("Consumer", "필수·임의소비재 섹터 추적"),
                      title="Consumer", url_path="consumer")
pg_logi = st.Page(_placeholder("Logistics / Commerce", "물류·커머스 섹터 추적"),
                  title="Logistics/Commerce", url_path="logistics-commerce")
pg_steel = st.Page(_placeholder("Steel & Non-Ferrous Metals", "철강·비철금속 섹터 추적"),
                   title="Steel & Non-Ferrous Metals", url_path="steel-metals")

from app_pages import cover  # noqa: E402  (st.page_link 에 Page 객체가 필요해 여기서 조립)

_PAGES = {"buzz": pg_buzz, "value": pg_value, "bio": pg_bio, "beauty": pg_beauty,
          "ent": pg_ent, "trailer": pg_trailer, "boxoffice": pg_boxoffice,
          "consumer": pg_consumer, "logi": pg_logi, "steel": pg_steel}


def _cover():
    cover.render(_PAGES)


pg_cover = st.Page(_cover, title="LK Asset Terminal", url_path="home", default=True)

nav = st.navigation({
    "": [pg_cover],
    "Screener": [pg_buzz, pg_value, pg_stock, pg_watch],
    "Sector Watch": [pg_bio, pg_beauty, pg_ent, pg_trailer, pg_boxoffice,
                     pg_consumer, pg_logi, pg_steel],
})
nav.run()
