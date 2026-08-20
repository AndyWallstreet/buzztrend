# -*- coding: utf-8 -*-
"""BABYMONSTER 2026 월드투어 트래커."""
import streamlit as st

from app_pages import yg_tour_common

st.set_page_config(page_title="BABYMONSTER 투어", page_icon="🎤", layout="wide")

yg_tour_common.render(
    artist="BABYMONSTER",
    tour_csv="babymonster_tour.csv",
    booking_csv="babymonster_booking.csv",
    ticker_note="종목: 와이지엔터테인먼트 (122870)",
)
