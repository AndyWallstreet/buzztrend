# -*- coding: utf-8 -*-
"""BIGBANG 2026-2027 월드투어(XX : COSMOS) 트래커."""
import streamlit as st

from app_pages import yg_tour_common

st.set_page_config(page_title="BIGBANG 투어", page_icon="🎤", layout="wide")

yg_tour_common.render(
    artist="BIGBANG",
    tour_csv="bigbang_tour.csv",
    booking_csv="bigbang_booking.csv",
    ticker_note="종목: 와이지엔터테인먼트 (122870)",
)
