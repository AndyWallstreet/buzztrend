# -*- coding: utf-8 -*-
"""LK Asset Terminal — 첫 화면 (블룸버그 터미널풍 커버).

router(streamlit_app.py)가 st.Page 객체 dict 를 넘겨 호출한다 —
st.page_link 가 함수 기반 페이지(플레이스홀더)를 가리키려면 객체가 필요해서다.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "hatchuping"
KST = timezone(timedelta(hours=9))


def _boxoffice():
    p = DATA / "boxoffice_now.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _egg():
    p = DATA / "ratings.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return df.iloc[-1] if len(df) else None


def render(pages: dict):
    st.markdown("""
    <style>
    .lk-hero { font-family: "SF Mono", Consolas, "Courier New", monospace; }
    .lk-hero h1 {
        color: #f5a623; letter-spacing: 0.06em; font-size: 2.6rem;
        margin-bottom: 0; font-weight: 800;
    }
    .lk-hero .sub { color: #8b919c; letter-spacing: 0.3em; font-size: 0.78rem;
                    text-transform: uppercase; margin-top: 0.2rem; }
    .lk-rule { border: none; border-top: 2px solid #f5a623; margin: 0.9rem 0 0.3rem 0; }
    .lk-strip { color: #565c66; font-family: Consolas, monospace; font-size: 0.75rem;
                letter-spacing: 0.12em; }
    .lk-sec { color: #f5a623; text-transform: uppercase; letter-spacing: 0.18em;
              font-size: 0.8rem; font-weight: 700; margin: 1.4rem 0 0.4rem 0;
              font-family: Consolas, monospace; }
    /* page_link 카드를 터미널 메뉴처럼 */
    [data-testid="stPageLink"] a {
        border: 1px solid #23262d; border-left: 3px solid #f5a623;
        border-radius: 0; padding: 0.55rem 0.9rem; background: #101318;
    }
    [data-testid="stPageLink"] a:hover { background: #1a1e25; border-color: #f5a623; }
    [data-testid="stPageLink"] a p { color: #d7dae0 !important; font-size: 0.93rem; }
    </style>
    """, unsafe_allow_html=True)

    now = datetime.now(KST)
    st.markdown(f"""
    <div class="lk-hero">
      <h1>◆ LK ASSET TERMINAL</h1>
      <div class="sub">LK Asset Management &nbsp;·&nbsp; Research &amp; Monitoring</div>
      <hr class="lk-rule">
      <div class="lk-strip">{now.strftime('%Y-%m-%d %a %H:%M')} KST &nbsp;|&nbsp; SEOUL
      &nbsp;|&nbsp; DATA: KOBIS · CGV · YOUTUBE · CAPITAL IQ &nbsp;|&nbsp; INTERNAL USE</div>
    </div>
    """, unsafe_allow_html=True)

    # ---- LIVE 스냅샷 (지금 실제로 추적 중인 숫자)
    bo, egg = _boxoffice(), _egg()
    if bo or egg is not None:
        st.markdown('<div class="lk-sec">■ Live — 하츄핑2 박스오피스</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        if bo:
            c1.metric(f"누적 관객수 (D+{bo['day']})", f"{bo['cum']:,}명",
                      f"하루 {bo['adm']:,}명 · {bo['rank']}위", delta_color="off")
            if bo.get("ratio_adj"):
                c2.metric("1편 같은 일차 대비", f"{bo['ratio_adj']:.2f}배",
                          "유료시사 제외 기준", delta_color="off")
            if bo.get("forecast"):
                c3.metric("최종 예상 관객수", f"{bo['forecast']:,}명",
                          f"1편 최종 {bo['m1_final']:,}명", delta_color="off")
        if egg is not None:
            c4.metric("CGV 에그지수", f"{int(egg['cgv_egg'])}%", "실관람객 평점", delta_color="off")

    # ---- 메뉴
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="lk-sec">■ Screener</div>', unsafe_allow_html=True)
        st.page_link(pages["buzz"], label="Buzz Trend — 소셜 언급량 모니터")
        st.page_link(pages["value"], label="Value Screener — 싸고 좋은 주식 찾기")
    with right:
        st.markdown('<div class="lk-sec">■ Sector Watch</div>', unsafe_allow_html=True)
        st.page_link(pages["ent"], label="Entertainment/Contents — Movie tracking")
        st.page_link(pages["trailer"], label="└ 하츄핑2 예고편 — 유튜브 · 예매율 기록")
        st.page_link(pages["boxoffice"], label="└ 하츄핑2 개봉 후 — KOBIS 실관객수 · 평점")
        st.page_link(pages["bio"], label="Bio/Healthcare — 준비 중")
        st.page_link(pages["beauty"], label="Cosmetics/Beauty — 준비 중")
        st.page_link(pages["consumer"], label="Consumer — 준비 중")
        st.page_link(pages["logi"], label="Logistics/Commerce — 준비 중")
        st.page_link(pages["steel"], label="Steel & Non-Ferrous Metals — 준비 중")

    st.markdown('<hr class="lk-rule" style="margin-top:1.6rem">', unsafe_allow_html=True)
    st.markdown('<div class="lk-strip">DAILY REFRESH 07:30 KST BY SCHEDULED TASK '
                '&nbsp;|&nbsp; SOURCE CODE: GITHUB/ANDYWALLSTREET/BUZZTREND</div>',
                unsafe_allow_html=True)
