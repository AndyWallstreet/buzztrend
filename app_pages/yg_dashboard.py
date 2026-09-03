# -*- coding: utf-8 -*-
"""YG 엔터테인먼트 (122870) 트래커 — 매출 축을 세 갈래로 나눠 본다.

책갈피(탭) 3개:
  📀 제품 매출   — 실물 앨범 판매량(Circle Chart) → 앨범 매출 추정
  🎤 콘서트 매출 — BIGBANG / BABYMONSTER 투어 트래커
  🎯 컨센서스 비트 — 2026E 컨센서스 추이 + 상반기 실적의 컨센서스 달성률

데이터: yg_album_export.py (앨범·컨센서스), yg_tour_export.py (투어),
       findb (DART 분기 실적).
"""
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from app_pages import yg_tour_common

DATA = Path(__file__).resolve().parent.parent / "data" / "yg"
FINDB = Path(__file__).resolve().parent.parent / "data" / "findb" / "financials.csv.gz"
TICKER = "A122870"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"

st.set_page_config(page_title="YG 트래커", page_icon="🎵", layout="wide")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 0.97rem; font-weight: 700; background: #16283e;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 6px 12px; margin: 0.9rem 0 0.5rem 0;
}
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


YEAR_C = 2026


@st.cache_data(show_spinner=False)
def load_circle(name, stamp):
    p = DATA / name
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(show_spinner=False)
def load_album(stamp):
    p = DATA / "album_sales.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return df[df["artist"] != "Sum"].copy()


@st.cache_data(show_spinner=False)
def load_consensus(stamp):
    p = DATA / "consensus.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    return df


@st.cache_data(show_spinner=False)
def load_actuals():
    if not FINDB.exists():
        return None
    f = pd.read_csv(FINDB)
    f = f[f["ticker"] == TICKER].sort_values("q")
    return f if len(f) else None


def _stamp(name):
    p = DATA / name
    return round(p.stat().st_mtime, 3) if p.exists() else 0.0


st.title("YG 엔터테인먼트 트래커")
st.caption("와이지엔터테인먼트 (122870) · 매출 3대 축 — 제품(앨범) · 콘서트 · "
           "컨센서스 대비 실적 | 출처: YG 분석 워크북 + DART")

tab_prod, tab_tour, tab_cons = st.tabs(
    ["📀 제품 매출 (앨범)", "🎤 콘서트 매출", "🎯 컨센서스 비트"])

# ------------------------------------------------------------------ 제품 매출
with tab_prod:
    alb = load_album(_stamp("album_sales.csv"))
    if alb is None or not len(alb):
        st.info("앨범 데이터가 없습니다 — `python yg_album_export.py` 를 먼저 실행하세요.")
    else:
        c1, c2 = st.columns([1, 3], gap="large")
        with c1:
            y_min, y_max = int(alb["year"].min()), int(alb["year"].max())
            y0, y1 = st.slider("기간", y_min, y_max, (max(y_min, y_max - 10), y_max),
                               key="yg_alb_yr")
            asp = st.number_input("앨범 ASP (원/장)", 5000, 60000, 30000, 1000,
                                  key="yg_asp",
                                  help="워크북 Album 시트 가정 기본값 30,000원. "
                                       "앨범 매출 = 판매량 × ASP")
        a = alb[(alb["year"] >= y0) & (alb["year"] <= y1)].copy()
        a["장수(만장)"] = a["copies"] / 1e4
        by_year = a.groupby("year", as_index=False).agg(
            copies=("copies", "sum"), est=("is_est", "max"))
        by_year["매출추정(억)"] = by_year["copies"] * asp / 1e8

        # 요약 지표 — 최근 실적 연도 기준
        act = by_year[~by_year["est"]]
        with c2:
            if len(act):
                last = act.iloc[-1]
                prev = act.iloc[-2] if len(act) >= 2 else None
                m1, m2, m3 = st.columns(3)
                m1.metric(f"{int(last['year'])}년 앨범 판매",
                          f"{last['copies'] / 1e4:,.0f}만장",
                          f"{(last['copies'] / prev['copies'] - 1) * 100:+.0f}% YoY"
                          if prev is not None and prev["copies"] else None)
                m2.metric(f"{int(last['year'])}년 앨범 매출 추정",
                          f"{last['copies'] * asp / 1e8:,.0f}억원",
                          f"ASP {asp:,}원 가정", delta_color="off")
                _top = (a[a["year"] == last["year"]]
                        .sort_values("copies", ascending=False))
                if len(_top):
                    m3.metric("최다 판매 아티스트", _top.iloc[0]["artist"],
                              f"{_top.iloc[0]['copies'] / 1e4:,.0f}만장",
                              delta_color="off")

        sub("연도별 앨범 판매량", "아티스트별 누적 · Circle Chart 집계 (E = 추정)")
        a["연도"] = a["year"].astype(str) + np.where(a["is_est"], "E", "")
        bars = alt.Chart(a).mark_bar(opacity=0.9).encode(
            x=alt.X("연도:N", sort=None, title=None),
            y=alt.Y("장수(만장):Q", title="앨범 판매 (만장)", stack=True),
            color=alt.Color("artist:N", title="아티스트",
                            legend=alt.Legend(orient="top", columns=5)),
            tooltip=["연도", "artist",
                     alt.Tooltip("장수(만장)", format=",.1f")])
        st.altair_chart(bars.properties(height=380), use_container_width=True)

        sub("앨범 매출 추정", f"판매량 × ASP {asp:,}원")
        by_year["연도"] = (by_year["year"].astype(str)
                          + np.where(by_year["est"], "E", ""))
        rev_bars = alt.Chart(by_year).mark_bar(opacity=0.9).encode(
            x=alt.X("연도:N", sort=None, title=None),
            y=alt.Y("매출추정(억):Q", title="앨범 매출 추정 (억원)"),
            color=alt.Color("est:N", title=None,
                            scale=alt.Scale(domain=[False, True],
                                            range=[C_BAR, C_LINE]),
                            legend=alt.Legend(orient="top",
                                              labelExpr="datum.label == 'true' "
                                                        "? '추정' : '실적'")),
            tooltip=["연도", alt.Tooltip("매출추정(억)", format=",.0f"),
                     alt.Tooltip("copies", format=",.0f", title="판매량(장)")])
        st.altair_chart(rev_bars.properties(height=300), use_container_width=True)
        st.caption("실물 앨범 판매량은 Circle Chart(구 가온) 집계 기준이며, 워크북 "
                   "Album 시트에서 가져옵니다. 매출 추정은 단순히 판매량 × ASP라 "
                   "실제 제품 매출(음원·MD 포함)과는 다릅니다.")

    # ---------------- 앨범별 상세 (Circle Chart 자동 수집) ----------------
    st.divider()
    sub("앨범별 상세 — Circle Chart 자동 수집",
        "월간(1월~) + 주간(7월~) · 그룹·앨범 단위 · 출하량-반품량 기준")
    cm = load_circle("yg_albums_monthly.csv", _stamp("yg_albums_monthly.csv"))
    cw = load_circle("yg_albums_weekly.csv", _stamp("yg_albums_weekly.csv"))
    if cm is None or not len(cm):
        st.info("Circle 데이터가 없습니다 — `python yg_circle_update.py` 를 실행하세요.")
    else:
        cm = cm.copy()
        cm["sales"] = cm["sales"].astype(float)
        cm["_m"] = cm["period"].str[5:7].astype(int)
        cm["분기"] = "Q" + ((cm["_m"] - 1) // 3 + 1).astype(str)

        q1, q2 = st.columns(2, gap="large")
        with q1:
            qq = cm.groupby(["분기", "group"], as_index=False)["sales"].sum()
            qq["만장"] = qq["sales"] / 1e4
            ch = alt.Chart(qq).mark_bar(opacity=0.9).encode(
                x=alt.X("분기:N", title=None),
                y=alt.Y("만장:Q", title="분기 판매 (만장)", stack=True),
                color=alt.Color("group:N", title=None,
                                legend=alt.Legend(orient="top")),
                tooltip=["분기", "group", alt.Tooltip("만장", format=",.1f")])
            st.altair_chart(ch.properties(height=300), use_container_width=True)
            _mmax = int(cm["_m"].max())
            st.caption(f"**읽는법**: 월간 차트 합산(현재 {YEAR_C}년 {_mmax}월까지 반영, "
                       "진행 중 분기는 미완성). 컴백 분기에 막대가 서는 구조라 분기 간 "
                       "낙차 자체가 정상 — 전년 같은 분기와 비교해야 함.")
        with q2:
            if cw is not None and len(cw):
                cwp = cw.copy()
                cwp["sales"] = cwp["sales"].astype(float)
                cwp["start"] = pd.to_datetime(cwp["start"])
                top_albums = (cwp.groupby("album")["sales"].sum()
                              .sort_values(ascending=False).head(6).index)
                ww = cwp[cwp["album"].isin(top_albums)]
                ch = alt.Chart(ww).mark_line(size=2, point=True).encode(
                    x=alt.X("start:T", title=None),
                    y=alt.Y("sales:Q", title="주간 판매 (장)"),
                    color=alt.Color("album:N", title=None,
                                    legend=alt.Legend(orient="top", columns=2,
                                                      labelLimit=180)),
                    tooltip=["album", alt.Tooltip("start:T", title="주 시작"),
                             alt.Tooltip("sales", format=",.0f")])
                st.altair_chart(ch.properties(height=300),
                                use_container_width=True)
                st.caption("**읽는법**: 주간 판매 상위 6개 앨범(7월 이후). 발매 첫 주 "
                           "초동이 치솟고 급감하는 게 정상 패턴 — 2주차 잔존율이 "
                           "높으면 팬덤 확장 신호. 톱100 밖으로 밀리면 선이 끊김.")

        # 앨범별 누적 테이블
        tot = (cm.groupby(["group", "album"], as_index=False)
               .agg(연간누적=("sales", "sum")))
        if cw is not None and len(cw):
            _lw = cw[cw["week"].astype(int) == cw["week"].astype(int).max()]
            _lwm = dict(zip(_lw["album"], _lw["sales"].astype(float)))
            tot["최근주간"] = tot["album"].map(_lwm)
        tot = tot.sort_values("연간누적", ascending=False)
        tot["연간누적"] = tot["연간누적"].map(lambda v: f"{v:,.0f}")
        tot["최근주간"] = tot["최근주간"].map(
            lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
        tot.columns = ["그룹", "앨범", f"{YEAR_C}년 누적(장)", "최근 주간(장)"]
        st.dataframe(tot, hide_index=True, use_container_width=True,
                     height=min(80 + 36 * len(tot), 420))
        st.caption("**읽는법**: 버전(KiT·LP·Weverse 등)은 별도 행. 누적은 월간 차트 "
                   "합산이라 톱100 밖 롱테일은 빠짐(과소집계). 갱신: "
                   "`python yg_circle_update.py` — 매일 배치에 포함돼 주간 차트가 "
                   "나오는 대로 자동 반영. 분기 마감 후 월간 3개가 모이면 Q3·Q4 "
                   "막대가 완성됨.")

# ------------------------------------------------------------------ 콘서트
with tab_tour:
    artist = st.radio("아티스트", ["BIGBANG", "BABYMONSTER"], horizontal=True,
                      key="yg_tour_artist")
    _cfg = {"BIGBANG": ("bigbang_tour.csv", "bigbang_booking.csv"),
            "BABYMONSTER": ("babymonster_tour.csv", "babymonster_booking.csv")}
    _tc, _bc = _cfg[artist]
    yg_tour_common.render(artist=artist, tour_csv=_tc, booking_csv=_bc,
                          ticker_note="종목: 와이지엔터테인먼트 (122870)")

# ------------------------------------------------------------------ 컨센서스
with tab_cons:
    cons = load_consensus(_stamp("consensus.csv"))
    act = load_actuals()
    if cons is None or not len(cons):
        st.info("컨센서스 데이터가 없습니다 — `python yg_album_export.py` 를 "
                "먼저 실행하세요.")
    else:
        cur = cons.iloc[-1]
        first = cons.iloc[0]
        _m3 = cons[cons["date"] >= cur["date"] - pd.Timedelta(days=90)].iloc[0]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("2026E 매출 컨센서스", f"{cur['rev_eok']:,.0f}억원",
                  f"3개월 {cur['rev_eok'] / _m3['rev_eok'] * 100 - 100:+.1f}%")
        m2.metric("2026E 영업이익 컨센서스", f"{cur['op_eok']:,.0f}억원",
                  f"3개월 {cur['op_eok'] / _m3['op_eok'] * 100 - 100:+.1f}%"
                  if _m3["op_eok"] else None)
        m3.metric("2026E 영업이익률", f"{cur['op_eok'] / cur['rev_eok'] * 100:.1f}%")
        m4.metric("참여 증권사", f"{int(cur['n_rev'])}곳",
                  f"1년 전 {int(first['n_rev'])}곳", delta_color="off")

        sub("컨센서스 추이", "1년간 2026년 연간 추정치가 어떻게 바뀌었나 "
                         "(올라가면 실적이 기대를 넘고 있다는 뜻)")
        cm = cons.melt("date", value_vars=["rev_eok", "op_eok"],
                       var_name="구분", value_name="억원")
        cm["구분"] = cm["구분"].map({"rev_eok": "매출 2026E",
                                   "op_eok": "영업이익 2026E"})
        base = alt.Chart(cm).encode(x=alt.X("date:T", title=None))
        rev_l = base.transform_filter(alt.datum.구분 == "매출 2026E").mark_line(
            color=C_BAR, size=2.5).encode(
            y=alt.Y("억원:Q", title="매출 컨센서스 (억원)",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="날짜"),
                     alt.Tooltip("억원", format=",.0f", title="매출 2026E")])
        op_l = base.transform_filter(alt.datum.구분 == "영업이익 2026E").mark_line(
            color=C_GOLD, size=2.5).encode(
            y=alt.Y("억원:Q", title="영업이익 컨센서스 (억원)",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="날짜"),
                     alt.Tooltip("억원", format=",.0f", title="영업이익 2026E")])
        st.altair_chart(alt.layer(rev_l, op_l).resolve_scale(y="independent")
                        .properties(height=340).interactive(),
                        use_container_width=True)
        st.caption("파랑 = 매출(왼쪽 축), 금색 = 영업이익(오른쪽 축). "
                   "출처: 워크북 Consensus 시트 (Quantiwise 일별 컨센서스).")

        # ---- 상반기 실적의 컨센서스 달성률
        if act is not None:
            yr = int(cons["date"].iloc[-1].year)
            ytd = act[act["q"].str.startswith(str(yr))]
            if len(ytd):
                sub("올해 실적 진행률", f"{yr}년 누적 실적이 연간 컨센서스의 몇 %인가")
                r_ytd = ytd["rev"].sum() / 1e8
                o_ytd = ytd["ebit"].sum() / 1e8
                nq = len(ytd)
                p1, p2, p3 = st.columns(3)
                p1.metric(f"{yr}년 누적 매출 ({nq}개 분기)", f"{r_ytd:,.0f}억원",
                          f"컨센서스의 {r_ytd / cur['rev_eok'] * 100:.0f}%",
                          delta_color="off")
                p2.metric(f"{yr}년 누적 영업이익", f"{o_ytd:,.0f}억원",
                          f"컨센서스의 {o_ytd / cur['op_eok'] * 100:.0f}%"
                          if cur["op_eok"] else None, delta_color="off")
                _pace = nq / 4 * 100
                p3.metric("단순 진도 기준", f"{_pace:.0f}%",
                          "이보다 높으면 초과 달성 페이스", delta_color="off")
                _gap = r_ytd / cur["rev_eok"] * 100 - _pace
                if _gap >= 3:
                    st.success(f"매출이 단순 진도({_pace:.0f}%)보다 "
                               f"**{_gap:+.0f}%p** 앞서 있습니다 — 컨센서스 상향 "
                               "여지가 있는 구간.")
                elif _gap <= -3:
                    st.warning(f"매출이 단순 진도({_pace:.0f}%)보다 "
                               f"**{_gap:+.0f}%p** 뒤쳐져 있습니다 — 하반기에 "
                               "몰아쳐야 컨센서스를 맞춥니다.")
                else:
                    st.info(f"매출이 단순 진도({_pace:.0f}%)와 비슷한 속도입니다.")
                st.caption("실적 = DART 분기보고서(연결) 누적, 컨센서스 = 위 차트의 "
                           "최신값. 엔터는 앨범 발매·투어 일정에 따라 분기 편차가 커서 "
                           "단순 진도(분기수÷4)와의 비교는 참고용입니다.")
