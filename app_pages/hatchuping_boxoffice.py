# -*- coding: utf-8 -*-
"""하츄핑 2 개봉 후 트래커 — KOBIS 확정 관객수와 실관람객 평점.

boxoffice_update.py / ratings_update.py 가 매일 아침 data/hatchuping/ 을 갱신한다.
예고편(유튜브) 추적은 hatchuping_trailer.py 페이지에 있다.
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "hatchuping"

C_M2 = "#2a78d6"   # 2편 (blue)
C_M1 = "#eb6834"   # 1편 (orange)

st.set_page_config(page_title="하츄핑2 개봉 후", page_icon="🎬", layout="wide")

LOAD_FILES = ("m1_daily.csv", "m2_daily.csv", "boxoffice_now.json",
              "ratings.csv", "sentiment_daily.csv", "ratings_peers.json")


def load_stamp():
    return tuple(round((DATA / f).stat().st_mtime, 3) if (DATA / f).exists() else 0.0
                 for f in LOAD_FILES)


@st.cache_data(show_spinner=False)
def load(stamp):
    def _csv(name):
        p = DATA / name
        return pd.read_csv(p, parse_dates=["date"]) if p.exists() else None

    def _json(name):
        p = DATA / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    return (_csv("m1_daily.csv"), _csv("m2_daily.csv"), _json("boxoffice_now.json"),
            _csv("ratings.csv"), _csv("sentiment_daily.csv"), _json("ratings_peers.json"))


def date_span(dates, extra_days=3):
    ds = pd.to_datetime(pd.Series(list(dates))).dt.normalize()
    return pd.date_range(ds.min(), ds.max() + pd.Timedelta(days=extra_days), freq="D")


def day_axis(days, max_labels=12):
    """실측 날짜에 눈금을 고정 — 짧은 구간을 넓은 차트에 그리면 같은 라벨이 반복돼서."""
    days = pd.DatetimeIndex(days)
    step = max(1, -(-len(days) // max_labels))
    return alt.Axis(format="%-m/%-d", values=[d.to_pydatetime() for d in days[::step]],
                    labelAngle=0, labelOverlap=False)


m1d, m2d, bonow, rat, sd, peer = load(load_stamp())

st.title("🎬 사랑의 하츄핑 2 — 개봉 후 트래커")
st.caption("2026-08-05 개봉 · KOBIS 확정 관객수 기준 · 1편(운명의 시작, 최종 1,239,245명)과 "
           "같은 일차 비교 · 예고편(유튜브) 추적은 '하츄핑2 예고편' 페이지에")

st.header("1. 개봉 후 실관객수 — 흥행 판정", divider="blue")
st.caption("개봉 후에는 예매율이 아니라 KOBIS **확정 관객수**가 진짜 숫자입니다. "
           "1편(2024-08-07 개봉)의 같은 일차와 나란히 놓고 봅니다 — "
           "1편 곡선이 자(尺)라서 억지 계수가 필요 없고, 관객이 빠지면 배수가 바로 떨어집니다.")

if m2d is None or not len(m2d):
    st.info("🎬 오늘 개봉했습니다 (2026-08-05). KOBIS 확정 관객수는 **다음날 아침**에 나옵니다 — "
            "내일 아침 첫 숫자가 여기에 채워집니다.")
elif m1d is None or not len(m1d):
    st.warning("1편 기준 곡선(m1_daily.csv)이 없습니다 — `python boxoffice_update.py --build-m1` 실행 필요")
else:
    m1_final = (bonow or {}).get("m1_final", 1239245)
    last_bo = m2d.iloc[-1]
    dnum = int(last_bo["day"])
    ref = m1d[m1d["day"] == dnum]
    prev = m2d.iloc[-2] if len(m2d) > 1 else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"누적 관객수 (개봉 {dnum + 1}일차)", f"{int(last_bo['cum']):,}명",
              f"어제 하루 {int(last_bo['adm']):,}명", delta_color="off")
    k2.metric("어제 하루 관객수", f"{int(last_bo['adm']):,}명",
              (f"{int(last_bo['adm'] - prev['adm']):+,} (그 전날보다)" if prev is not None
               else f"{int(last_bo['rank'])}위"))
    if len(ref):
        r = ref.iloc[0]
        # 유료시사(개봉일 누적 - 당일)를 빼고 비교한다 — 1편 49,683 vs 2편 27,410 으로
        # 출발선이 달라서, 생 누적끼리 재면 개봉 직후 2편이 실제보다 나빠 보인다.
        m2p = int((bonow or {}).get("m2_preview", 0))
        m1p = int((bonow or {}).get("m1_preview", 0))
        adj2, adj1 = int(last_bo["cum"]) - m2p, int(r["cum"]) - m1p
        ratio = adj2 / max(1, adj1)
        k3.metric(f"1편 같은 일차(D+{dnum}) 대비", f"{ratio:.2f}배",
                  f"개봉 후 누적 {adj2:,} vs 1편 {adj1:,}명 (유료시사 제외)", delta_color="off")
        k4.metric("최종 예상 관객수", f"{ratio * m1_final:,.0f}명",
                  f"= {ratio:.2f}배 × 1편 최종 {m1_final:,}명", delta_color="off")
    else:
        k3.metric(f"1편 같은 일차(D+{dnum}) 대비", "비교 불가", "1편 곡선 범위 밖", delta_color="off")
        k4.metric("최종 예상 관객수", "—", "배수 계산 불가", delta_color="off")

    # ---- 숫자 비교표 — 그래프만 보면 "얼마나"가 안 잡힌다. 같은 일차의 실제 값을
    # 1편/2편 나란히, 배수까지 한 표에 적는다.
    if len(ref):
        rr = ref.iloc[0]

        def _n(row, col):
            v = pd.to_numeric(pd.Series([row.get(col)]), errors="coerce").iloc[0]
            return None if pd.isna(v) else float(v)

        def _fmt(v, pct=False):
            if v is None:
                return "—"
            return f"{v:.1%}" if pct else f"{v:,.0f}"

        rows_tbl = []

        def add(label, col, pct=False, v1=None, v2=None):
            a1 = _n(rr, col) if v1 is None else v1
            a2 = _n(last_bo, col) if v2 is None else v2
            ratio = (a2 / a1) if (a1 and a2 is not None) else None
            rows_tbl.append({
                "항목": label,
                "1편": _fmt(a1, pct),
                "2편": _fmt(a2, pct),
                "1편 대비": f"{ratio:.2f}배" if ratio else "—",
            })

        add(f"하루 관객수 (개봉 {dnum + 1}일차)", "adm")
        add("누적 관객수", "cum")
        add("누적 — 유료시사 제외", "cum", v1=adj1, v2=adj2)
        add("스크린수", "screens")
        add("스크린점유율", "screen_share", pct=True)
        add("상영횟수", "shows")
        add("상영점유율", "show_share", pct=True)
        add("좌석점유율", "seat_rate", pct=True)
        md = ["| 항목 | 1편 | 2편 | 1편 대비 |", "|---|---:|---:|---:|"]
        for t_ in rows_tbl:
            md.append(f"| {t_['항목']} | {t_['1편']} | **{t_['2편']}** | **{t_['1편 대비']}** |")
        st.markdown("\n".join(md))
        st.caption(f"같은 일차(개봉 {dnum + 1}일차) 기준 · 1편 = 2024-08-07 개봉 · "
                   "'1편 대비'가 1.00배보다 크면 1편보다 잘하고 있다는 뜻입니다")

    # ---- 누적 곡선 비교 (같은 일차끼리)
    span = max(int(m2d["day"].max()) + 7, 14)
    a = m2d[["day", "cum", "adm", "screens"]].copy()
    a["구분"] = "2편"
    b = m1d[m1d["day"] <= span][["day", "cum", "adm", "screens"]].copy()
    b["구분"] = "1편"
    comp = pd.concat([a, b], ignore_index=True)

    base = alt.Chart(comp).encode(
        x=alt.X("day:Q", title="개봉 후 경과일 (0 = 개봉일)",
                scale=alt.Scale(domain=[0, span], nice=False),
                axis=alt.Axis(tickMinStep=1, format="d")),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                 range=[C_M2, C_M1]),
                        legend=alt.Legend(title=None, orient="top-left")))
    cum_line = base.mark_line(point=True, strokeWidth=2.5).encode(
        y=alt.Y("cum:Q", title="누적 관객수", axis=alt.Axis(format=",.0f")),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                           range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                 alt.Tooltip("cum:Q", title="누적", format=","),
                 alt.Tooltip("adm:Q", title="당일", format=","),
                 alt.Tooltip("screens:Q", title="스크린", format=",")])
    st.altair_chart(cum_line.properties(height=340), width="stretch")
    _m2p = int((bonow or {}).get("m2_preview", 0))
    _m1p = int((bonow or {}).get("m1_preview", 0))
    st.caption(f"⚫ 파란 실선 = 2편 · 주황 점선 = 1편 (최종 {m1_final:,}명) · 같은 경과일끼리 비교 · "
               f"그래프의 누적에는 유료시사(1편 {_m1p:,}명 / 2편 {_m2p:,}명)가 포함돼 있어 "
               "출발선이 다릅니다 — 위의 배수는 그 시사분을 뺀 값입니다")

    # ---- 일별 유입 관객수 — 누적은 과거를 다 안고 가서 둔하다. 하루치는 오늘의 힘을
    # 그대로 보여주고, 주말 봉우리가 얼마나 높고 평일 골이 얼마나 얕은지로 뒷심이 읽힌다.
    st.markdown("#### 하루 관객수 (일별 유입)")
    day_line = base.mark_line(point=True, strokeWidth=2.5).encode(
        y=alt.Y("adm:Q", title="하루 관객수", axis=alt.Axis(format=",.0f")),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                           range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                 alt.Tooltip("adm:Q", title="하루 관객", format=","),
                 alt.Tooltip("cum:Q", title="누적", format=","),
                 alt.Tooltip("screens:Q", title="스크린", format=",")])
    st.altair_chart(day_line.properties(height=300), width="stretch")

    # 하루치 배수는 누적보다 먼저 움직인다 — 추세가 꺾이는 날 바로 드러나는 조기 신호.
    d_ratio = None
    if len(ref) and int(ref["adm"].iloc[0]) > 0:
        d_ratio = int(last_bo["adm"]) / int(ref["adm"].iloc[0])
    st.caption(
        (f"오늘 하루치 배수 **{d_ratio:.2f}배** (2편 {int(last_bo['adm']):,}명 vs "
         f"1편 같은 일차 {int(ref['adm'].iloc[0]):,}명) — 하루치 배수 × 1편 최종 = "
         f"**{d_ratio * m1_final:,.0f}명**. " if d_ratio else "")
        + "누적은 지나간 날을 다 안고 가서 천천히 움직이지만, 하루치는 그날의 힘을 바로 보여줍니다 — "
          "그래서 흐름이 꺾이면 하루치 배수가 먼저 떨어집니다. "
          "1편은 주말(개봉 3·4일차)에 121,522 / 109,050명까지 솟았다가 평일에 1.5만 명대로 "
          "내려앉는 톱니 모양이었습니다. 2편의 봉우리가 그보다 높고 골이 얕으면 최종은 더 커집니다.")

    # ---- 공급(스크린·상영횟수)과 그 점유율 — 전부 1편과 두 줄로 비교
    # 왼쪽 = 절대량, 오른쪽 = 시장에서 차지한 비중. 절대량만 보면 그 해 전체 극장 물량이
    # 달라서 착시가 생긴다 (2026년 시장이 2024년보다 작다).
    supply = pd.concat([
        m2d.assign(구분="2편"),
        m1d[m1d["day"] <= span].assign(구분="1편"),
    ], ignore_index=True)
    for col in ("screens", "shows", "screen_share", "show_share", "seat_rate"):
        if col in supply:
            supply[col] = pd.to_numeric(supply[col], errors="coerce")

    def vs_chart(ycol, ytitle, pct=False):
        return alt.Chart(supply.dropna(subset=[ycol])).mark_line(point=True).encode(
            x=alt.X("day:Q", title="경과일", scale=alt.Scale(domain=[0, span], nice=False),
                    axis=alt.Axis(tickMinStep=1, format="d")),
            y=alt.Y(f"{ycol}:Q", title=ytitle,
                    axis=alt.Axis(format=".0%" if pct else ",.0f")),
            color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                     range=[C_M2, C_M1]), legend=None),
            strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                               range=[[1, 0], [5, 4]]), legend=None),
            tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                     alt.Tooltip(f"{ycol}:Q", title=ytitle,
                                 format=".1%" if pct else ",.0f")],
        ).properties(height=220)

    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**스크린수 — 공급이 줄면 관객도 준다**")
        st.altair_chart(vs_chart("screens", "스크린수"), width="stretch")
    with a2:
        st.markdown("**스크린점유율 — 그날 전체 스크린 중 몇 %**")
        st.altair_chart(vs_chart("screen_share", "스크린점유율", pct=True), width="stretch")

    b1, b2 = st.columns(2)
    with b1:
        st.markdown("**상영횟수 — 하루에 몇 번 트나**")
        st.altair_chart(vs_chart("shows", "상영횟수"), width="stretch")
    with b2:
        st.markdown("**상영점유율 — 그날 전체 상영 중 몇 %**")
        st.altair_chart(vs_chart("show_share", "상영점유율", pct=True), width="stretch")

    st.markdown("**좌석점유율 — 수요의 질 (관객 ÷ 상영횟수×160석)**")
    st.altair_chart(vs_chart("seat_rate", "좌석점유율", pct=True), width="stretch")
    st.caption("위 네 개는 극장이 이 영화에 **얼마나 걸어줬나(공급)**, 좌석점유율은 "
               "관객이 **얼마나 채웠나(수요)** 입니다. 공급은 극장이 정하고 수요는 관객이 정하므로, "
               "좌석점유율이 높으면 다음 주 스크린이 늘어나는 쪽으로 이어집니다 — 그래서 남겨 뒀습니다.")

    st.caption("판단 기준선 — **124만** 넘으면 1편 초과(기본 성공) · **200만** = 예매가 약속한 수준 "
               "(D-1 예매 1.62배) · **250만** = 회귀 상단. 1편은 첫 주말(개봉 4일차)까지 "
               "누적 406,384명으로 최종의 32.8%를 벌었습니다 — 즉 첫 주말 누적 × 약 3.05 ≈ 최종.")

st.divider()
st.header("2. 실관람객 평점 & 반응", divider="blue")
st.caption("**에그지수**는 CGV에서 그 영화 표를 실제로 산 사람만 매길 수 있는 점수라, "
           "공개된 숫자 중 실관람객 만족도에 가장 가깝습니다. "
           "가족 애니메이션은 입소문이 뒷심을 만들기 때문에, 관객수가 꺾이기 전에 "
           "여기서 먼저 신호가 나옵니다.")

if rat is None or not len(rat):
    st.info("아직 평점 수집 전입니다 — 개봉일부터 매일 쌓입니다.")
else:
    rlast = rat.iloc[-1]
    rprev = rat.iloc[-2] if len(rat) > 1 else None
    peers = [p for p in ((peer or {}).get("peers") or []) if p.get("egg")]
    peer_avg = sum(p["egg"] for p in peers) / len(peers) if peers else None

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("CGV 에그지수 (실관람객)", f"{int(rlast['cgv_egg'])}%",
              (f"{int(rlast['cgv_egg'] - rprev['cgv_egg']):+d}%p (어제보다)"
               if rprev is not None else "수집 시작"),
              delta_color="normal" if rprev is not None else "off")
    if peer_avg:
        g2.metric("가족·애니 평균 대비", f"{int(rlast['cgv_egg']) - peer_avg:+.1f}%p",
                  f"동시상영 {len(peers)}편 평균 {peer_avg:.1f}%", delta_color="off")
    if sd is not None and len(sd):
        slast = sd.iloc[-1]
        sprev = sd.iloc[-2] if len(sd) > 1 else None
        g3.metric("댓글 긍정 비율", f"{slast['pos_ratio']:.0%}",
                  (f"{(slast['pos_ratio'] - sprev['pos_ratio']) * 100:+.1f}%p (어제보다)"
                   if sprev is not None else f"댓글 {int(slast['total']):,}개"),
                  delta_color="normal" if sprev is not None else "off")
        g4.metric("댓글 부정 비율", f"{slast['neg_ratio']:.0%}",
                  f"부정 {int(slast['neg'] + slast['strong_neg'])}개 / {int(slast['total']):,}개",
                  delta_color="inverse" if sprev is not None else "off")

    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**에그지수 추이**")
        eg = rat[["date", "cgv_egg"]].copy()
        line = alt.Chart(eg).mark_line(point=True, strokeWidth=2.5, color=C_M2).encode(
            x=alt.X("date:T", title=None, axis=day_axis(date_span(eg["date"], 3))),
            y=alt.Y("cgv_egg:Q", title="에그지수 (%)",
                    scale=alt.Scale(domain=[max(50, int(eg["cgv_egg"].min()) - 8), 100])),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                     alt.Tooltip("cgv_egg:Q", title="에그지수")])
        layers = [line]
        if peers:
            pdf = pd.DataFrame(peers)
            layers.append(alt.Chart(pdf).mark_rule(
                color="#8a8f98", strokeDash=[4, 4], strokeWidth=1).encode(
                y="egg:Q", tooltip=[alt.Tooltip("name:N", title="비교작"),
                                    alt.Tooltip("egg:Q", title="에그지수")]))
        st.altair_chart(alt.layer(*layers).properties(height=260), width="stretch")
        if peers:
            st.caption("회색 점선 = 같이 상영 중인 가족·애니메이션 에그지수 · "
                       + " · ".join(f"{p['name']} {p['egg']}%" for p in peers[:4]))
    with e2:
        st.markdown("**댓글 긍부정 비율 추이**")
        if sd is not None and len(sd) >= 1:
            mix = sd.melt(id_vars=["date"], value_vars=["pos_ratio", "neg_ratio"],
                          var_name="구분", value_name="비율")
            mix["구분"] = mix["구분"].map({"pos_ratio": "긍정", "neg_ratio": "부정"})
            ch = alt.Chart(mix).mark_line(point=True, strokeWidth=2.2).encode(
                x=alt.X("date:T", title=None, axis=day_axis(date_span(sd["date"], 3))),
                y=alt.Y("비율:Q", title="비율", axis=alt.Axis(format=".0%")),
                color=alt.Color("구분:N", scale=alt.Scale(domain=["긍정", "부정"],
                                                         range=["#2a9d5c", "#d64545"]),
                                legend=alt.Legend(title=None, orient="top-left")),
                tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                         alt.Tooltip("구분:N"), alt.Tooltip("비율:Q", format=".1%")])
            st.altair_chart(ch.properties(height=260), width="stretch")
            st.caption("메인 예고편 댓글 5단계 자동 분류 기준 (강한긍정+긍정 = 긍정) · "
                       "**실관람평이 아니라 예고편 댓글**입니다 — 실관람평은 극장 사이트가 "
                       "자동 수집을 막아 두어 대신 에그지수로 봅니다")
        else:
            st.info("댓글 감성 데이터가 아직 없습니다.")

st.divider()
