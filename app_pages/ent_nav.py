# -*- coding: utf-8 -*-
"""Entertainment 섹터 공용 좌측 메뉴 — 회사 페이지들이 같이 쓴다."""
import streamlit as st


def sidebar():
    with st.sidebar:
        st.markdown("**🏢 [Entertainment / Contents](/entertainment)**")
        st.caption("SAMG 엔터 (419530)")
        st.page_link("app_pages/hatchuping_trailer.py", label="🐳 하츄핑2 예고편")
        st.page_link("app_pages/hatchuping_boxoffice.py", label="🎬 하츄핑2 개봉 후")
        st.caption("YG 엔터 (122870)")
        st.page_link("app_pages/yg_dashboard.py", label="🎵 YG 트래커")
        st.divider()
