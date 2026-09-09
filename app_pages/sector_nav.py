# -*- coding: utf-8 -*-
"""Sector Watch 공용 좌측 메뉴 — 모든 섹터·회사 페이지가 같이 쓴다.

sidebar("ent") 처럼 현재 섹터 키를 넘기면: 전체 섹터 목록을 보여주고,
현재 섹터만 펼쳐서 회사·페이지 링크를 나열한다.
새 회사 페이지를 만들면 여기 SECTORS와 streamlit_app.py 상단바 플라이아웃
두 곳에 같이 추가할 것.
"""
import streamlit as st

# key, 표시 이름, URL, [(회사 캡션, [(등록된 페이지 경로 or '/URL', 라벨)])]
SECTORS = [
    ("batt", "Batteries / EV / ESS", "/batteries", []),
    ("bio", "Bio / Healthcare", "/bio-healthcare", []),
    ("beauty", "Cosmetics / Beauty", "/cosmetics-beauty", [
        ("동국제약 (086450)", [
            ("app_pages/cosmetics.py", "💄 센텔리안24 미국 수요"),
            ("/종목상세?ticker=A086450", "📋 동국제약 Stock Picker"),
        ]),
    ]),
    ("ent", "Entertainment / Contents", "/entertainment", [
        ("SAMG 엔터 (419530)", [
            ("app_pages/hatchuping_trailer.py", "🐳 하츄핑2 예고편"),
            ("app_pages/hatchuping_boxoffice.py", "🎬 하츄핑2 개봉 후"),
        ]),
        ("YG 엔터 (122870)", [
            ("app_pages/yg_dashboard.py", "🎵 YG 트래커"),
        ]),
    ]),
    ("consumer", "Consumer", "/consumer", []),
    ("logi", "Logistics / Commerce", "/logistics-commerce", []),
    ("steel", "Steel & Non-Ferrous Metals", "/steel-metals", []),
]


def sidebar(current: str):
    with st.sidebar:
        st.markdown("**📊 SECTOR WATCH**")
        for key, label, url, comps in SECTORS:
            if key != current:
                st.markdown(f'<a href="{url}" target="_self" style="display:block;'
                            'padding:3px 0;color:#93a1b5;text-decoration:none;'
                            f'font-size:0.9rem">{label}</a>',
                            unsafe_allow_html=True)
                continue
            st.markdown(f'<a href="{url}" target="_self" style="display:block;'
                        'padding:3px 0;color:#7cb3ff;font-weight:700;'
                        'text-decoration:none;border-left:3px solid #2e7de9;'
                        f'padding-left:8px">{label}</a>', unsafe_allow_html=True)
            for caption, pages in comps:
                st.caption(caption)
                for path, plabel in pages:
                    if path.startswith("/"):
                        st.markdown(f'<a href="{path}" target="_self" '
                                    'style="display:block;padding:2px 0 2px 14px;'
                                    'color:#c6d0de;text-decoration:none;'
                                    f'font-size:0.88rem">{plabel}</a>',
                                    unsafe_allow_html=True)
                    else:
                        st.page_link(path, label=plabel)
            if not comps:
                st.caption("└ 회사별 페이지 준비 중")
        st.divider()
