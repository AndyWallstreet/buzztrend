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
              "ratings.csv", "sentiment_daily.csv", "ratings_peers.json",
              "board_daily.csv", "board_samples.json")


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
            _csv("ratings.csv"), _csv("sentiment_daily.csv"), _json("ratings_peers.json"),
            _csv("board_daily.csv"), _json("board_samples.json"))


def date_span(dates, extra_days=3):
    ds = pd.to_datetime(pd.Series(list(dates))).dt.normalize()
    return pd.date_range(ds.min(), ds.max() + pd.Timedelta(days=extra_days), freq="D")


def day_axis(days, max_labels=12):
    """실측 날짜에 눈금을 고정 — 짧은 구간을 넓은 차트에 그리면 같은 라벨이 반복돼서."""
    days = pd.DatetimeIndex(days)
    step = max(1, -(-len(days) // max_labels))
    return alt.Axis(format="%-m/%-d", values=[d.to_pydatetime() for d in days[::step]],
                    labelAngle=0, labelOverlap=False)


m1d, m2d, bonow, rat, sd, peer, bd, bsamp = load(load_stamp())

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
st.header("3. 네이버 종목토론방 — SAMG엔터 (419530)", divider="blue")
st.caption("주주들이 지금 무슨 얘기를 하는지. 게시글 **제목**을 주식 어휘 키워드로 긍/부정 분류합니다 — "
           "거친 분류이니 비율의 **추세**와 아래 실제 글 제목을 같이 보세요. "
           "오늘 행은 진행 중 스냅샷이라 하루 종일 숫자가 커집니다.")

if bd is None or not len(bd):
    st.info("아직 수집 전입니다 — 매일 아침 자동으로 쌓입니다.")
else:
    bdd = bd.sort_values("date").reset_index(drop=True)
    b_last = bdd.iloc[-1]
    b_full = bdd.iloc[-2] if len(bdd) > 1 else None    # 마지막 '완결된' 하루 = 어제

    n1, n2, n3, n4 = st.columns(4)
    _bl = pd.Timestamp(b_last["date"])
    n1.metric(f"오늘 게시글 ({_bl.month}/{_bl.day})",
              f"{int(b_last['posts']):,}건", "진행 중", delta_color="off")
    if b_full is not None:
        prev2 = bdd.iloc[-3] if len(bdd) > 2 else None
        n2.metric("어제 게시글", f"{int(b_full['posts']):,}건",
                  (f"{int(b_full['posts'] - prev2['posts']):+,} (그제보다)" if prev2 is not None else "—"))
        n3.metric("어제 긍정 비율", f"{b_full['pos_ratio']:.0%}",
                  f"긍정 {int(b_full['pos'])}건 / {int(b_full['posts'])}건", delta_color="off")
        n4.metric("어제 부정 비율", f"{b_full['neg_ratio']:.0%}",
                  f"부정 {int(b_full['neg'])}건 / {int(b_full['posts'])}건", delta_color="off")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**하루 게시글 수 — 관심의 크기**")
        bar = alt.Chart(bdd).mark_bar(color=C_M2).encode(
            x=alt.X("date:T", title=None, axis=day_axis(date_span(bdd["date"], 2))),
            y=alt.Y("posts:Q", title="게시글 수"),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                     alt.Tooltip("posts:Q", title="게시글"),
                     alt.Tooltip("pos:Q", title="긍정"), alt.Tooltip("neg:Q", title="부정")])
        st.altair_chart(bar.properties(height=240), width="stretch")
    with g2:
        st.markdown("**긍정 vs 부정 비율 — 분위기의 방향**")
        mix = bdd.melt(id_vars=["date"], value_vars=["pos_ratio", "neg_ratio"],
                       var_name="구분", value_name="비율")
        mix["구분"] = mix["구분"].map({"pos_ratio": "긍정", "neg_ratio": "부정"})
        ln = alt.Chart(mix).mark_line(point=True, strokeWidth=2.2).encode(
            x=alt.X("date:T", title=None, axis=day_axis(date_span(bdd["date"], 2))),
            y=alt.Y("비율:Q", title="비율", axis=alt.Axis(format=".0%")),
            color=alt.Color("구분:N", scale=alt.Scale(domain=["긍정", "부정"],
                                                     range=["#2a9d5c", "#d64545"]),
                            legend=alt.Legend(title=None, orient="top-left")),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                     alt.Tooltip("구분:N"), alt.Tooltip("비율:Q", format=".1%")])
        st.altair_chart(ln.properties(height=240), width="stretch")

    if bsamp:
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("**주요 긍정 글** (최근 3일 · 조회·공감 순)")
            for p in (bsamp.get("top_pos") or [])[:6]:
                st.markdown(f"- {p['title']}  \n"
                            f"  <span style='color:#8b919c;font-size:0.8em'>"
                            f"{p['date'][5:]} · 조회 {p['views']:,}"
                            + (f" · 공감 {p['agree']}" if p.get("agree") else "")
                            + "</span>", unsafe_allow_html=True)
            if not bsamp.get("top_pos"):
                st.caption("긍정 분류된 글이 없습니다.")
        with p2:
            st.markdown("**주요 부정 글** (최근 3일 · 조회·공감 순)")
            for p in (bsamp.get("top_neg") or [])[:6]:
                st.markdown(f"- {p['title']}  \n"
                            f"  <span style='color:#8b919c;font-size:0.8em'>"
                            f"{p['date'][5:]} · 조회 {p['views']:,}"
                            + (f" · 공감 {p['agree']}" if p.get("agree") else "")
                            + "</span>", unsafe_allow_html=True)
            if not bsamp.get("top_neg"):
                st.caption("부정 분류된 글이 없습니다.")
        st.caption(f"수집: {bsamp.get('as_of', '')} · finance.naver.com 종목토론방 · "
                   "제목 키워드 분류 (긍정: 매수/상승/흥행/대박 계열, 부정: 하락/손절/매도/실망 계열) · "
                   "주가 얘기와 영화 얘기가 섞여 있습니다")


# ================= 4. 언급량 추이 (트레일러 페이지에서 이동)
st.divider()
st.header("4. 언급량 추이", divider="blue")
buzz_path = DATA / "buzz_daily.csv"
if not buzz_path.exists():
    st.info("준비 중입니다 — 커뮤니티·뉴스·검색 언급량을 모아서 곧 추가할 예정입니다.")
else:
    bz = pd.read_csv(buzz_path, parse_dates=["date"])
    M1_OPEN, M2_OPEN = pd.Timestamp(2024, 8, 7), pd.Timestamp(2026, 8, 5)

    # ---- ① 주가 vs 언급량 (전체 기간, 엑셀 'Stock price vs SNS comment count' 차트와 동일)
    sp_path = DATA / "stock_price.csv"
    if sp_path.exists():
        st.markdown("#### ① 주가 vs 언급량")
        C_STOCK = "#4ade80"   # 주가 — 밝은 초록 (어두운 배경에서도 주황 막대와 확실히 구분)
        sp = pd.read_csv(sp_path, parse_dates=["date"])
        start = max(bz["date"].min(), sp["date"].min())
        bz_full = bz[bz["date"] >= start]
        sp_full = sp[sp["date"] >= start]
        # size=1 → one thin bar per day. Vega-Lite's default continuousBandSize is 5,
        # which at ~1,460 daily points smears the series into a solid block; the Excel
        # 'Stock price vs SNS comment count' chart this mirrors uses hairline bars.
        bars_sp = alt.Chart(bz_full).mark_bar(color=C_M1, opacity=0.7, size=1).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%Y-%m", labelAngle=0)),
            y=alt.Y("total:Q", title="언급량 (일별 합계)", axis=alt.Axis(format=",.0f")),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                     alt.Tooltip("total:Q", title="언급량", format=",.0f")])
        line_sp = alt.Chart(sp_full).mark_line(color=C_STOCK, strokeWidth=1.6).encode(
            x="date:T",
            y=alt.Y("price:Q", title="SAMG엔터 주가 (원)", axis=alt.Axis(format=",.0f"),
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                     alt.Tooltip("price:Q", title="주가", format=",.0f")])
        rules_sp = pd.DataFrame({"x": [M1_OPEN, M2_OPEN], "t": ["1편 개봉", "2편 개봉"]})
        rule_sp = alt.Chart(rules_sp).mark_rule(color="#8a8f98", strokeDash=[3, 3],
                                                strokeWidth=1.1).encode(
            x="x:T", tooltip=[alt.Tooltip("t:N", title="")])
        lab_sp = alt.Chart(rules_sp).mark_text(color="#8a8f98", fontSize=11, dx=4, align="left",
                                               baseline="top").encode(
            x="x:T", y=alt.value(4), text="t:N")
        st.altair_chart(alt.layer(bars_sp, rule_sp, lab_sp, line_sp)
                        .resolve_scale(y="independent").properties(height=340),
                        width="stretch")
        st.caption("🟧 막대 = 하츄핑/티니핑 언급량 (왼쪽 축) · 🟢 선 = SAMG엔터(419530) 주가 (오른쪽 축) · "
                   "점선 = 1편·2편 개봉일 — 1편 개봉 직후 언급량 폭발 구간과 주가 흐름을 함께 볼 수 있습니다")

    # ---- ② 1편 vs 2편 D-day 비교
    st.markdown("#### ② 1편 vs 2편 비교 (개봉일 기준)")
    st.caption("썸트렌드 '하츄핑/티니핑' 언급량 (커뮤니티+인스타그램+블로그+뉴스+유튜브 합계) · "
               "개봉일 기준 D-day 정렬 — 1편(2024-08-07)과 2편(2026-08-05)의 같은 시점끼리 비교")

    def dlab(d):
        return "개봉일" if d == 0 else (f"D+{d}" if d > 0 else f"D-{-d}")

    cs = st.columns([1, 1, 2])
    win = cs[0].selectbox("롤링 기간", [1, 2, 3, 7], index=3,
                          format_func=lambda n: f"{n}일 롤링")
    how = cs[1].selectbox("집계 방식", ["합계", "평균"])

    # 하루라도 빠진 날이 있으면 그 구간 롤링은 NaN — 없는 숫자를 지어내지 않는다
    s = bz.set_index("date")["total"].asfreq("D")
    roll = s.rolling(win, min_periods=win)
    rs = roll.sum() if how == "합계" else roll.mean()

    dd = pd.DataFrame({"d": range(-40, 31)})
    dd["1편 (2024)"] = [rs.get(M1_OPEN + pd.Timedelta(days=int(k))) for k in dd["d"]]
    dd["2편 (2026)"] = [rs.get(M2_OPEN + pd.Timedelta(days=int(k))) for k in dd["d"]]
    dd["YoY"] = dd["2편 (2026)"] / dd["1편 (2024)"] - 1

    # ---- KPI: 가장 최근 비교 가능한 D-day
    d_now = (bz["date"].max() - M2_OPEN).days
    row_now = dd[dd["d"] == d_now]
    if len(row_now) and pd.notna(row_now.iloc[0]["2편 (2026)"]) and pd.notna(row_now.iloc[0]["1편 (2024)"]):
        v1, v2 = row_now.iloc[0]["1편 (2024)"], row_now.iloc[0]["2편 (2026)"]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"2편 언급량 ({dlab(d_now)}, {win}일 {how})", f"{v2:,.0f}")
        c2.metric(f"1편 같은 시점 ({dlab(d_now)})", f"{v1:,.0f}", delta_color="off")
        c3.metric("YoY (2편 ÷ 1편 − 1)", f"{v2 / v1 - 1:+.1%}",
                  "1편보다 화제성 앞섬" if v2 > v1 else "1편보다 화제성 뒤짐",
                  delta_color="normal" if v2 > v1 else "inverse")

    # ---- chart: 1편 vs 2편 lines on D-day axis
    axis_d = alt.Axis(labelExpr="datum.value == 0 ? '개봉' : "
                                "(datum.value > 0 ? 'D+' + datum.value : 'D-' + -datum.value)",
                      values=list(range(-40, 31, 5)), labelAngle=0)
    long = dd.melt("d", ["1편 (2024)", "2편 (2026)"], var_name="영화", value_name="값").dropna()
    lines = alt.Chart(long).mark_line(strokeWidth=2.2, interpolate="monotone").encode(
        x=alt.X("d:Q", title="개봉일 기준 D-day", axis=axis_d, scale=alt.Scale(domain=[-40, 30])),
        y=alt.Y("값:Q", title=f"언급량 ({win}일 {how})", axis=alt.Axis(format=",.0f")),
        color=alt.Color("영화:N",
                        scale=alt.Scale(domain=["1편 (2024)", "2편 (2026)"], range=[C_M1, C_M2]),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[alt.Tooltip("d:Q", title="D-day"), alt.Tooltip("영화:N"),
                 alt.Tooltip("값:Q", title="언급량", format=",.0f")])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
        color="#8a8f98", strokeDash=[3, 3], strokeWidth=1.2).encode(x="x:Q")
    st.altair_chart((lines + zero).properties(height=320), width="stretch")

    # ---- chart: YoY bars
    st.markdown("**2편이 1편보다 몇 % 더 화제인가 (같은 D-day끼리)**")
    ydf = dd.dropna(subset=["YoY"])
    bars = alt.Chart(ydf).mark_bar(size=7, color=C_M2, cornerRadiusTopLeft=2,
                                   cornerRadiusTopRight=2).encode(
        x=alt.X("d:Q", title="개봉일 기준 D-day", axis=axis_d, scale=alt.Scale(domain=[-40, 30])),
        y=alt.Y("YoY:Q", title="YoY", axis=alt.Axis(format="+.0%")),
        tooltip=[alt.Tooltip("d:Q", title="D-day"), alt.Tooltip("YoY:Q", format="+.1%"),
                 alt.Tooltip("1편 (2024):Q", title="1편", format=",.0f"),
                 alt.Tooltip("2편 (2026):Q", title="2편", format=",.0f")])
    st.altair_chart((bars + zero).properties(height=240), width="stretch")
    st.caption("참고: 티니핑 프랜차이즈 자체가 2024년보다 커져서, YoY의 일부는 영화가 아닌 "
               "브랜드 성장분일 수 있습니다. 그래도 모든 D-day에서 1편 곡선 위에 있으면 좋은 신호.")

    with st.expander("매일 기록 표 (언급량, 채널별)"):
        st.dataframe(bz.sort_values("date", ascending=False), hide_index=True, width="stretch")
    st.caption("데이터: 썸트렌드(some.co.kr) · 엑셀 원본: Heartuping movie 2_Buzz trend_v1.xlsx "
               "'D-day 비교' 시트와 동일한 계산")

