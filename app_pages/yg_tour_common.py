# -*- coding: utf-8 -*-
"""YG 투어 트래커 공용 렌더러 — BIGBANG / BABYMONSTER 페이지가 함께 쓴다.

데이터는 yg_tour_export.py 가 워크북에서 뽑아 둔 data/yg/*.csv 를 읽는다.
예매 스냅샷(bigbang_booking.csv 등)은 yg_booking_update.py 로 쌓는다.
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "yg"

C_REGION = {"KR": "#2a78d6", "JP": "#e0508c", "NA/EU": "#eb6834", "Others": "#4fae62"}
REGION_KO = {"KR": "한국", "JP": "일본", "NA/EU": "북미·유럽", "Others": "아시아·기타"}


def _stamp(files):
    return tuple(round((DATA / f).stat().st_mtime, 3) if (DATA / f).exists() else 0.0
                 for f in files)


@st.cache_data(show_spinner=False)
def _load(tour_csv, booking_csv, stamp):
    tour = pd.read_csv(DATA / tour_csv, parse_dates=["date"])
    p = DATA / booking_csv
    booking = (pd.read_csv(p, parse_dates=["asof", "tour_date"])
               if p.exists() and p.stat().st_size > 60 else None)
    a = DATA / "assumptions.json"
    assum = json.loads(a.read_text(encoding="utf-8")) if a.exists() else {}
    return tour, booking, assum


def _fmt_eok(mn):
    """₩mn → 억원 문자열."""
    return f"{mn / 100:,.0f}억"


def render(artist, tour_csv, booking_csv, ticker_note):
    tour, booking, assum = _load(tour_csv, booking_csv,
                                 _stamp([tour_csv, booking_csv, "assumptions.json"]))
    today = pd.Timestamp.now().normalize()
    tour_name = tour["tour"].iloc[0] if len(tour) else ""

    st.title(f"{artist} 투어 트래커")
    st.caption(f"{tour_name} · 출처: YG 분석 워크북 Tour detail (Wikipedia/Namuwiki 기반) · {ticker_note}")

    # ---- 상단 지표
    done = tour[tour["date"] < today]
    nxt = tour[tour["date"] >= today].head(1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("도시 스탑", f"{len(tour)}곳 · {int(tour['shows'].sum())}회")
    c2.metric("총 좌석", f"{int(tour['seats'].sum()):,}석")
    c3.metric("YG 매출 추정 (전체 투어)", _fmt_eok(tour["yg_rev_krw_mn"].sum()),
              help="관객수(좌석×95%) × 지역 티켓가격 × 인식률 × 환율 1,500")
    if len(nxt):
        n = nxt.iloc[0]
        dd = (n["date"] - today).days
        c4.metric("다음 공연", f"{n['city']} {'D-DAY' if dd == 0 else f'D-{dd}'}",
                  f"{n['date']:%m/%d} · {n['venue']}", delta_color="off")
    else:
        c4.metric("다음 공연", "투어 종료", f"완료 {len(done)}곳", delta_color="off")

    # ---- 1. 투어 캘린더
    st.subheader("1. 투어 캘린더", divider="blue")
    st.caption("막대 높이 = 좌석수(수용인원×회차). 색 = 지역 → 지역이 티켓가격과 매출 인식률을 정한다.")

    cal = tour.copy()
    cal["status"] = cal["date"].apply(lambda d: "완료" if d < today else "예정")
    bars = alt.Chart(cal).mark_bar(size=14).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%y-%m")),
        y=alt.Y("seats:Q", title="좌석수", axis=alt.Axis(format=",.0f")),
        color=alt.Color("region:N", scale=alt.Scale(domain=list(C_REGION),
                        range=list(C_REGION.values())),
                        legend=alt.Legend(title=None, orient="top-left")),
        opacity=alt.condition(alt.datum.status == "완료", alt.value(0.45), alt.value(1)),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("city:N", title="도시"), alt.Tooltip("venue:N", title="공연장"),
                 alt.Tooltip("shows:Q", title="회차"),
                 alt.Tooltip("seats:Q", title="좌석", format=","),
                 alt.Tooltip("yg_rev_krw_mn:Q", title="YG 매출(₩mn)", format=",.0f")])
    rule = (alt.Chart(pd.DataFrame({"d": [today]})).mark_rule(
        color="#eb6834", strokeDash=[4, 3]).encode(x="d:T"))
    st.altair_chart((bars + rule).properties(height=260), use_container_width=True)

    view = cal[["date", "city", "country", "venue", "capacity", "shows", "seats",
                "price_usd", "att_est", "yg_rev_krw_mn", "status"]].copy()
    view["date"] = view["date"].dt.strftime("%Y-%m-%d (%a)")
    view["yg_rev_억"] = (view.pop("yg_rev_krw_mn") / 100).round(1)
    view.columns = ["날짜", "도시", "국가", "공연장", "수용인원", "회차", "좌석 합계",
                    "티켓 $", "관객 추정", "상태", "YG 매출 추정(억)"]
    st.dataframe(view, use_container_width=True, hide_index=True,
                 column_config={
                     "수용인원": st.column_config.NumberColumn(format="%,d"),
                     "좌석 합계": st.column_config.NumberColumn(format="%,d"),
                     "관객 추정": st.column_config.NumberColumn(format="%,d"),
                 })

    # ---- 2. 월별·분기별 매출 추정
    st.subheader("2. 월별 · 분기별 매출 추정", divider="blue")
    st.caption("공연이 열리는 달에 매출을 인식한다고 가정. "
               f"티켓가격(1인): 한국 ${assum.get('price_usd', {}).get('KR', 100)} · "
               f"일본 ${assum.get('price_usd', {}).get('JP', 125)} · "
               f"북미·유럽 ${assum.get('price_usd', {}).get('NA/EU', 200)} · "
               f"기타 ${assum.get('price_usd', {}).get('Others', 80)} / "
               "인식률: 한국 40%(자체제작 총액) · 일본 30%(YGEX) · 그외 35%(개런티) / "
               f"환율 {assum.get('fx', 1500):,}원")

    mon = (tour.groupby(["month", "region"], as_index=False)["yg_rev_krw_mn"].sum())
    mon["억원"] = mon["yg_rev_krw_mn"] / 100
    ch_m = alt.Chart(mon).mark_bar(size=26).encode(
        x=alt.X("month:N", title=None, sort=None),
        y=alt.Y("억원:Q", title="YG 매출 추정 (억원)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("region:N", scale=alt.Scale(domain=list(C_REGION),
                        range=list(C_REGION.values())), legend=None),
        tooltip=[alt.Tooltip("month:N", title="월"),
                 alt.Tooltip("region:N", title="지역"),
                 alt.Tooltip("억원:Q", title="억원", format=",.1f")])
    st.altair_chart(ch_m.properties(height=240), use_container_width=True)

    q = tour.groupby("quarter", as_index=False).agg(
        스탑=("city", "count"), 회차=("shows", "sum"), 좌석=("seats", "sum"),
        관객_추정=("att_est", "sum"), 매출_mn=("yg_rev_krw_mn", "sum"))
    q["YG 매출 추정(억)"] = (q.pop("매출_mn") / 100).round(0)
    q.columns = ["분기", "스탑", "회차", "좌석", "관객 추정", "YG 매출 추정(억)"]
    st.dataframe(q, use_container_width=True, hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%,d")
                                for c in ["좌석", "관객 추정", "YG 매출 추정(억)"]})

    # ---- 3. 예매율 추적
    st.subheader("3. 예매율 추적", divider="blue")
    st.caption("스탑별로 '판매된 좌석 ÷ 전체 좌석'을 시간순으로 기록 — 모델 가정(95% 판매)에 "
               "실제로 얼마나 다가가는지 본다. 예매가 가정에 못 미치면 위 매출 추정을 내려야 한다.")

    if booking is None or booking.empty:
        st.info("아직 예매 스냅샷이 없습니다. 기록 방법: "
                "`python yg_booking_update.py --city Goyang --sold 37000` "
                "(총좌석은 캘린더에서 자동으로 찾음)")
        return

    booking = booking.sort_values("asof")
    latest = booking.groupby("city").tail(1)

    # 최신 예매율 vs 모델 가정
    prog = latest.merge(tour[["city", "date", "seats", "yg_rev_krw_mn"]], on="city")
    prog["예매율"] = prog["seats_sold"] / prog["seats_total"]
    cols = st.columns(min(4, max(1, len(prog))))
    for i, (_, r) in enumerate(prog.iterrows()):
        cols[i % len(cols)].metric(
            f"{r['city']} ({r['date']:%m/%d})",
            f"{r['예매율']:.0%} 판매",
            f"{int(r['seats_sold']):,} / {int(r['seats_total']):,}석",
            delta_color="off")

    # 스냅샷 추이
    booking["예매율"] = booking["seats_sold"] / booking["seats_total"]
    line = alt.Chart(booking).mark_line(point=True).encode(
        x=alt.X("asof:T", title=None),
        y=alt.Y("예매율:Q", title="판매된 좌석 비율", axis=alt.Axis(format=".0%")),
        color=alt.Color("city:N", legend=alt.Legend(title=None, orient="top-left")),
        tooltip=[alt.Tooltip("asof:T", title="기록일"), alt.Tooltip("city:N", title="도시"),
                 alt.Tooltip("seats_sold:Q", title="판매", format=","),
                 alt.Tooltip("예매율:Q", format=".1%")])
    target = alt.Chart(pd.DataFrame({"y": [0.95]})).mark_rule(
        color="#eb6834", strokeDash=[4, 3]).encode(y="y:Q")
    st.altair_chart((line + target).properties(height=240), use_container_width=True)
    st.caption("주황 점선 = 모델 가정(좌석의 95% 판매). ")
