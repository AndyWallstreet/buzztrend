# -*- coding: utf-8 -*-
"""Sector Watch 공용 좌측 메뉴 — 모든 섹터·회사 페이지가 같이 쓴다.

- 평소엔 섹터 이름만 보이고, 마우스를 올리면(hover) 그 섹터의 회사·페이지가
  펼쳐진다 (상단바 플라이아웃과 같은 동작, CSS만 사용).
- 링크는 st.page_link → SPA 전환이라 흰 화면 새로고침이 없다.
- Page 객체는 streamlit_app.py가 시작할 때 register()로 넣어준다
  (함수 페이지도 링크 가능해짐).
새 회사 페이지 추가 시: SECTORS + streamlit_app.py의 register 매핑 +
상단바 플라이아웃 세 곳을 같이 갱신할 것.
"""
import streamlit as st

_PAGES = {}


def register(pages: dict):
    """key -> st.Page 객체. streamlit_app.py가 nav.run() 전에 호출."""
    _PAGES.update(pages)


# (섹터 키, 표시 이름, [(회사 캡션, [(페이지 키 or '/URL', 라벨)])])
SECTORS = [
    ("batt", "Batteries / EV / ESS", []),
    ("bio", "Bio / Healthcare", []),
    ("beauty", "Cosmetics / Beauty", [
        ("동국제약 (086450)", [
            ("beauty", "💄 센텔리안24 미국 수요"),
            ("/종목상세?ticker=A086450", "📋 동국제약 Stock Picker"),
        ]),
    ]),
    ("ent", "Entertainment / Contents", [
        ("SAMG 엔터 (419530)", [
            ("trailer", "🐳 하츄핑2 예고편"),
            ("boxoffice", "🎬 하츄핑2 개봉 후"),
        ]),
        ("YG 엔터 (122870)", [
            ("yg", "🎵 YG 트래커"),
        ]),
    ]),
    ("consumer", "Consumer", []),
    ("logi", "Logistics / Commerce", []),
    ("steel", "Steel & Non-Ferrous Metals", []),
]

# 섹터 묶음(st.container key=secnav_*)의 첫 요소(섹터 링크)만 보이고,
# 나머지는 그 묶음에 마우스를 올렸을 때만 보이게 한다.
_CSS = """<style>
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  { gap: 0.2rem; }
/* 회사 이름(캡션) 위에 숨 쉴 공간 */
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  [data-testid="stCaptionContainer"] { margin-top: 0.55rem; }
/* 하위 페이지 링크(ㄴ …)는 회사 이름보다 오른쪽으로 들여쓰기 */
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  > div:not(:first-child) div[data-testid="stPageLink"]
  { padding-left: 20px; }
/* 섹터 이름과 회사 이름의 첫 글자를 같은 세로선에 맞춘다 */
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  > div:first-child a[data-testid="stPageLink-NavLink"]
  { padding-left: 2px; }
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  [data-testid="stCaptionContainer"] { padding-left: 2px; }
section[data-testid="stSidebar"] [class*="st-key-secnav_"]
  > div:not(:first-child) { display: none; }
section[data-testid="stSidebar"] [class*="st-key-secnav_"]:hover
  > div:not(:first-child) { display: block; }
section[data-testid="stSidebar"] [class*="st-key-secnav_"]:hover
  { background: #0e1626; border-radius: 6px; }
</style>"""


def sidebar(current: str):
    with st.sidebar:
        st.markdown(_CSS, unsafe_allow_html=True)
        st.markdown("**📊 SECTOR WATCH**")
        for key, label, comps in SECTORS:
            with st.container(key=f"secnav_{key}"):
                pg = _PAGES.get(key)
                lbl = f"🔹 {label}" if key == current else label
                if pg is not None:
                    st.page_link(pg, label=lbl)
                else:
                    st.markdown(lbl)
                for caption, pages in comps:
                    st.caption(caption)
                    for ref, plabel in pages:
                        if ref.startswith("/"):
                            st.markdown(
                                f'<a href="{ref}" target="_self" style="display:'
                                'block;padding:2px 0 2px 26px;color:#c6d0de;'
                                'text-decoration:none;font-size:0.88rem">'
                                f'ㄴ {plabel}</a>', unsafe_allow_html=True)
                        elif ref in _PAGES:
                            st.page_link(_PAGES[ref], label=f"ㄴ {plabel}")
                if not comps:
                    st.caption("ㄴ 회사별 페이지 준비 중")
        st.divider()
