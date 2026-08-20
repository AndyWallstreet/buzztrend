# -*- coding: utf-8 -*-
"""LK Terminal — 전체 내비게이션 (st.navigation 라우터).

실제 화면은 app_pages/ 아래 파일들이고, 이 파일은 사이드바 구조와
공통 테마(블룸버그풍 다크)만 정한다. Streamlit Cloud 의 entry point 라서
파일 이름은 streamlit_app.py 그대로 둔다.
"""
import streamlit as st

st.set_page_config(page_title="LK Terminal", page_icon="◆", layout="wide")

# ---- Epic Finance풍: 네이비-블루 배경 + 상단 고정 메뉴바 (호버 드롭다운)
st.markdown("""
<style>
/* 기본 상단 헤더는 숨기고 우리 메뉴바로 대체 */
header[data-testid="stHeader"] { display: none; }
.block-container { padding-top: 4rem !important; }
/* 본문/사이드바 배경 — 파이낸스 네이비 */
[data-testid="stAppViewContainer"] { background: #0c1320; }
[data-testid="stSidebar"] {
    background: #0a111c;
    border-right: 1px solid #1c2a3f;
}
/* 지표 숫자 — 터미널처럼 등폭 숫자 */
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
h1, h2, h3 { letter-spacing: -0.01em; }

/* ---- 상단 고정 메뉴바 ---- */
.lk-topbar {
    position: fixed; top: 0; left: 0; right: 0; height: 46px;
    background: #0a0f18;
    border-bottom: 1px solid #1c2a3f;
    display: flex; align-items: center;
    padding: 0 18px;
    z-index: 999999;
}
.lk-logo {
    font-weight: 800; font-size: 1.02rem; color: #e8edf5;
    margin-right: 22px; letter-spacing: -0.01em; white-space: nowrap;
}
.lk-logo .lk-chip {
    background: #2e7de9; color: #fff; border-radius: 4px;
    padding: 1px 7px; font-size: 0.7rem; margin-left: 6px; vertical-align: 2px;
}
.lk-menu { position: relative; height: 46px; display: flex; align-items: center; }
.lk-menu > a {
    color: #aeb9c9; text-decoration: none; font-size: 0.9rem; font-weight: 600;
    padding: 0 16px; height: 46px; line-height: 46px; display: block;
    white-space: nowrap;
}
.lk-menu:hover > a {
    color: #fff; background: #121b2b;
    box-shadow: inset 0 -2px 0 #2e7de9;
}
.lk-drop {
    display: none; position: absolute; top: 46px; left: 0; min-width: 235px;
    background: #0e1626; border: 1px solid #1c2a3f; border-top: none;
    padding: 7px 0; box-shadow: 0 14px 34px rgba(0,0,0,0.55);
}
.lk-menu:hover .lk-drop { display: block; }
.lk-drop a {
    display: block; padding: 9px 18px; color: #c6d0de;
    text-decoration: none; font-size: 0.88rem;
}
.lk-drop a:hover { background: #16223a; color: #7cb3ff; }
.lk-drop .lk-sub { padding-left: 36px; font-size: 0.82rem; color: #93a1b5; }
.lk-drop .lk-co {
    display: block; padding: 8px 18px 3px; font-size: 0.72rem; font-weight: 700;
    color: #5f7089; letter-spacing: 0.06em; text-transform: uppercase;
    border-top: 1px solid #16223a; margin-top: 4px;
}
.lk-drop .lk-co:first-child { border-top: none; margin-top: 0; }
</style>
<div class="lk-topbar">
  <span class="lk-logo">LK<span class="lk-chip">Terminal</span></span>
  <div class="lk-menu"><a href="/home" target="_self">Home</a></div>
  <div class="lk-menu"><a href="/밸류_스크리너" target="_self">Screener ▾</a>
    <div class="lk-drop">
      <a href="/buzz" target="_self">Buzz Trend</a>
      <a href="/밸류_스크리너" target="_self">Value Screener</a>
      <a href="/종목상세" target="_self">Stock Picker</a>
      <a href="/watchlist" target="_self">Watchlist</a>
    </div>
  </div>
  <div class="lk-menu"><a href="/entertainment" target="_self">Sector Watch ▾</a>
    <div class="lk-drop">
      <a href="/bio-healthcare" target="_self">Bio / Healthcare</a>
      <a href="/cosmetics-beauty" target="_self">Cosmetics / Beauty</a>
      <a href="/entertainment" target="_self">Entertainment / Contents</a>
      <span class="lk-co">SAMG Entertainment</span>
      <a class="lk-sub" href="/하츄핑2_예고편" target="_self">└ 하츄핑2 예고편</a>
      <a class="lk-sub" href="/하츄핑2_개봉후" target="_self">└ 하츄핑2 개봉 후</a>
      <span class="lk-co">YG Entertainment</span>
      <a class="lk-sub" href="/bigbang_tour" target="_self">└ BIGBANG Tour 2026</a>
      <a class="lk-sub" href="/babymonster_tour" target="_self">└ BABYMONSTER 2026</a>
      <a href="/consumer" target="_self">Consumer</a>
      <a href="/logistics-commerce" target="_self">Logistics / Commerce</a>
      <a href="/steel-metals" target="_self">Steel &amp; Non-Ferrous Metals</a>
    </div>
  </div>
</div>
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
pg_bigbang = st.Page("app_pages/yg_bigbang.py", title="└ BIGBANG Tour 2026",
                     url_path="bigbang_tour")
pg_babymon = st.Page("app_pages/yg_babymonster.py", title="└ BABYMONSTER 2026",
                     url_path="babymonster_tour")


def _entertainment():
    st.title("Entertainment / Contents")
    st.caption("엔터·콘텐츠 섹터 — 진행 중인 추적 (회사별)")
    st.subheader("SAMG Entertainment (419530)", divider="orange")
    st.page_link(pg_trailer, label="1. 하츄핑2 예고편 — 유튜브 조회수·댓글, 개봉 전 예매율 기록")
    st.page_link(pg_boxoffice, label="2. 하츄핑2 개봉 후 — KOBIS 실관객수, 실관람객 평점")
    st.caption("사랑의 하츄핑 2: 고래보석의 전설 (2026-08-05 개봉)")
    st.subheader("YG Entertainment (122870)", divider="orange")
    st.page_link(pg_bigbang, label="1. BIGBANG Tour 2026 — XX : COSMOS 월드투어 일정·예매율·매출 추정")
    st.page_link(pg_babymon, label="2. BABYMONSTER 2026 — 월드투어 일정·매출 추정")
    st.caption("투어 좌석·가격 가정: YG 분석 워크북 (Tour detail / Assumptions)")


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
          "bigbang": pg_bigbang, "babymon": pg_babymon,
          "consumer": pg_consumer, "logi": pg_logi, "steel": pg_steel}


def _cover():
    cover.render(_PAGES)


pg_cover = st.Page(_cover, title="LK Asset Terminal", url_path="home", default=True)

# 좌측 사이드바 내비 대신 상단 메뉴바를 쓰므로 내비는 숨긴다
# (Buzz Trend처럼 페이지 자체 사이드바 위젯이 있으면 그것만 표시된다)
nav = st.navigation({
    "": [pg_cover],
    "Screener": [pg_buzz, pg_value, pg_stock, pg_watch],
    "Sector Watch": [pg_bio, pg_beauty, pg_ent, pg_trailer, pg_boxoffice,
                     pg_bigbang, pg_babymon,
                     pg_consumer, pg_logi, pg_steel],
}, position="hidden")
nav.run()
