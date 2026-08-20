# -*- coding: utf-8 -*-
"""YG 투어 트래커 공용 렌더러 — BIGBANG / BABYMONSTER 페이지가 함께 쓴다.

데이터는 yg_tour_export.py 가 워크북에서 뽑아 둔 data/yg/*.csv 를 읽는다.
예매 스냅샷(bigbang_booking.csv 등)은 yg_booking_update.py 로 쌓는다.
스냅샷은 숫자(판매좌석)가 있으면 숫자로, 없으면 상태(매진/판매중)로 기록한다
— 고양처럼 쿠팡플레이 앱 전용이라 좌석수를 못 긁는 스탑이 있어서다.
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "yg"

C_REGION = {"KR": "#2a78d6", "JP": "#e0508c", "NA/EU": "#eb6834", "Others": "#4fae62"}
STATUS_BADGE = {"매진": "🔴 매진", "추가판매": "🟠 추가좌석 판매중", "판매중": "🟢 판매중",
                "미오픈": "⚪ 예매 전"}


def _stamp(files):
    return tuple(round((DATA / f).stat().st_mtime, 3) if (DATA / f).exists() else 0.0
                 for f in files)


@st.cache_data(show_spinner=False)
def _load(tour_csv, booking_csv, stamp):
    tour = pd.read_csv(DATA / tour_csv, parse_dates=["date"])
    p = DATA / booking_csv
    booking = None
    if p.exists():
        b = pd.read_csv(p, parse_dates=["asof", "tour_date"])
        if len(b):
            booking = b.sort_values("asof")
    a = DATA / "assumptions.json"
    assum = json.loads(a.read_text(encoding="utf-8")) if a.exists() else {}
    return tour, booking, assum


def _fmt_eok(mn):
    """₩mn → 억원 문자열."""
    return f"{mn / 100:,.0f}억"


def _status_text(row):
    """스냅샷 한 줄 → 사람이 읽는 예매상태. speed 가 있으면 '매진 (22분)' 식으로."""
    txt = None
    if isinstance(row.get("status"), str) and row["status"]:
        txt = STATUS_BADGE.get(row["status"], row["status"])
    elif pd.notna(row.get("fill")):
        txt = f"{row['fill']:.0%} 판매"
    if txt and isinstance(row.get("speed"), str) and row["speed"]:
        txt += f" ({row['speed']})"
    return txt


def render(artist, tour_csv, booking_csv, ticker_note):
    tour, booking, assum = _load(tour_csv, booking_csv,
                                 _stamp([tour_csv, booking_csv, "assumptions.json"]))
    today = pd.Timestamp.now().normalize()
    tour_name = tour["tour"].iloc[0] if len(tour) else ""

    st.title(f"{artist} 투어 트래커")
    st.caption(f"{tour_name} · 출처: YG 분석 워크북 Tour detail (Wikipedia/Namuwiki 기반) · {ticker_note}")

    # 스탑별 최신 예매 스냅샷
    latest = (booking.groupby("city").tail(1).set_index("city")
              if booking is not None else pd.DataFrame())

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
        sub = f"{n['date']:%m/%d} · {n['venue']}"
        if n["city"] in latest.index:
            stx = _status_text(latest.loc[n["city"]])
            if stx:
                sub += f" · {stx}"
        c4.metric("다음 공연", f"{n['city']} {'D-DAY' if dd == 0 else f'D-{dd}'}",
                  sub, delta_color="off")
    else:
        c4.metric("다음 공연", "투어 종료", f"완료 {len(done)}곳", delta_color="off")

    # ---- 1. 투어 캘린더 + 예매 현황 (스탑별 가로 막대)
    st.subheader("1. 투어 캘린더 · 예매 현황", divider="blue")
    st.caption("한 줄 = 한 도시. 옅은 막대 = 전체 좌석, 진한 막대 = 예매된 좌석. "
               "색 = 지역(티켓가격·인식률 결정). 숫자를 못 구하는 예매처(쿠팡플레이 등)는 "
               "매진/판매중 상태로 표시.")

    cal = tour.copy()
    cal["label"] = cal["date"].dt.strftime("%m/%d ") + cal["city"]
    cal["status"] = None
    cal["sold_seats"] = 0.0
    cal["badge"] = ""
    for city, row in latest.iterrows():
        m = cal["city"] == city
        if not m.any():
            continue
        stx = _status_text(row)
        cal.loc[m, "badge"] = stx or ""
        if isinstance(row.get("status"), str) and row["status"] == "매진":
            cal.loc[m, "sold_seats"] = cal.loc[m, "seats"]          # 매진 = 전량
        elif pd.notna(row.get("fill")):
            cal.loc[m, "sold_seats"] = cal.loc[m, "seats"] * row["fill"]
    cal.loc[cal["date"] < today, "badge"] = cal.loc[cal["date"] < today, "badge"].where(
        cal.loc[cal["date"] < today, "badge"] != "", "공연 완료")
    order = cal.sort_values("date")["label"].tolist()

    base = alt.Chart(cal).encode(
        y=alt.Y("label:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=220, labelFontSize=12)))
    total_bar = base.mark_bar(size=16, opacity=0.28).encode(
        x=alt.X("seats:Q", title="좌석수", axis=alt.Axis(format=",.0f")),
        color=alt.Color("region:N", scale=alt.Scale(domain=list(C_REGION),
                        range=list(C_REGION.values())),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("city:N", title="도시"), alt.Tooltip("venue:N", title="공연장"),
                 alt.Tooltip("shows:Q", title="회차"),
                 alt.Tooltip("seats:Q", title="전체 좌석", format=","),
                 alt.Tooltip("badge:N", title="예매상태"),
                 alt.Tooltip("yg_rev_krw_mn:Q", title="YG 매출(₩mn)", format=",.0f")])
    sold_bar = base.mark_bar(size=16).encode(
        x=alt.X("sold_seats:Q"),
        color=alt.Color("region:N", scale=alt.Scale(domain=list(C_REGION),
                        range=list(C_REGION.values())), legend=None))
    badge_txt = base.mark_text(align="left", dx=6, fontSize=11.5,
                               color="#e8edf5").encode(
        x=alt.X("seats:Q"), text="badge:N")
    st.altair_chart((total_bar + sold_bar + badge_txt)
                    .properties(height=26 * len(cal) + 40), use_container_width=True)

    view = cal[["date", "city", "country", "venue", "capacity", "shows", "seats",
                "price_usd", "badge", "yg_rev_krw_mn"]].copy()
    view["date"] = view["date"].dt.strftime("%Y-%m-%d (%a)")
    view["badge"] = view["badge"].replace("", "—")
    view["yg_rev_억"] = (view.pop("yg_rev_krw_mn") / 100).round(1)
    view.columns = ["날짜", "도시", "국가", "공연장", "수용인원", "회차", "좌석 합계",
                    "티켓 $", "예매상태", "YG 매출 추정(억)"]
    st.dataframe(view, use_container_width=True, hide_index=True,
                 column_config={
                     "수용인원": st.column_config.NumberColumn(format="%,d"),
                     "좌석 합계": st.column_config.NumberColumn(format="%,d"),
                 })

    # ---- 2. 월별·분기별 매출 추정
    st.subheader("2. 월별 · 분기별 매출 추정", divider="blue")
    # \$ : Streamlit 마크다운이 $...$ 를 수식으로 해석하므로 이스케이프
    st.caption("공연이 열리는 달에 매출을 인식한다고 가정. "
               f"티켓가격(1인): 한국 \\${assum.get('price_usd', {}).get('KR', 100)} · "
               f"일본 \\${assum.get('price_usd', {}).get('JP', 125)} · "
               f"북미·유럽 \\${assum.get('price_usd', {}).get('NA/EU', 200)} · "
               f"기타 \\${assum.get('price_usd', {}).get('Others', 80)} / "
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

    # ---- 3. 예매 기록
    st.subheader("3. 예매 기록", divider="blue")
    st.caption("스냅샷을 시간순으로 쌓아 모델 가정(좌석 95% 판매)에 실제로 얼마나 "
               "다가가는지 본다. 예매가 가정에 못 미치면 위 매출 추정을 내려야 한다.")

    if booking is None:
        st.info("아직 예매 스냅샷이 없습니다. 기록 방법: "
                "`python yg_booking_update.py --city Goyang --sold 37000` 또는 "
                "`--status 매진` (총좌석은 캘린더에서 자동으로 찾음)")
        return

    # 최신 상태 카드
    prog = latest.reset_index().merge(tour[["city", "date", "seats"]], on="city")
    cols = st.columns(min(4, max(1, len(prog))))
    for i, (_, r) in enumerate(prog.iterrows()):
        stx = _status_text(r) or "—"
        sub = (f"{int(r['seats_sold']):,} / {int(r['seats_total']):,}석"
               if pd.notna(r.get("seats_sold")) and pd.notna(r.get("seats_total"))
               else f"전체 {int(r['seats']):,}석")
        cols[i % len(cols)].metric(f"{r['city']} ({r['date']:%m/%d})", stx, sub,
                                   delta_color="off")

    # 숫자 스냅샷이 쌓이면 추이 선
    num = booking.dropna(subset=["fill"]) if "fill" in booking.columns else pd.DataFrame()
    if len(num):
        line = alt.Chart(num).mark_line(point=True).encode(
            x=alt.X("asof:T", title=None),
            y=alt.Y("fill:Q", title="판매된 좌석 비율", axis=alt.Axis(format=".0%")),
            color=alt.Color("city:N", legend=alt.Legend(title=None, orient="top-left")),
            tooltip=[alt.Tooltip("asof:T", title="기록일"),
                     alt.Tooltip("city:N", title="도시"),
                     alt.Tooltip("fill:Q", format=".1%")])
        target = alt.Chart(pd.DataFrame({"y": [0.95]})).mark_rule(
            color="#eb6834", strokeDash=[4, 3]).encode(y="y:Q")
        st.altair_chart((line + target).properties(height=240),
                        use_container_width=True)
        st.caption("주황 점선 = 모델 가정(좌석의 95% 판매).")

    # 기록 원본
    hist = booking.sort_values("asof", ascending=False).copy()
    hist["asof"] = hist["asof"].dt.strftime("%Y-%m-%d")
    hist["tour_date"] = hist["tour_date"].dt.strftime("%Y-%m-%d")
    if "speed" not in hist.columns:
        hist["speed"] = ""
    hist = hist[["asof", "city", "tour_date", "status", "speed", "seats_sold",
                 "seats_total", "fill", "note", "source"]]
    hist.columns = ["기록일", "도시", "공연일", "상태", "매진 속도", "판매좌석",
                    "총좌석", "판매율", "메모", "출처"]
    st.dataframe(hist, use_container_width=True, hide_index=True,
                 column_config={
                     "출처": st.column_config.LinkColumn("출처", display_text="링크"),
                     "판매율": st.column_config.NumberColumn(format="percent"),
                 })
