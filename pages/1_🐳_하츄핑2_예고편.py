# -*- coding: utf-8 -*-
"""하츄핑 2 예고편 트래커 — 유튜브 성적을 매일 추적, 1편과 비교.

Data files in data/hatchuping/ are refreshed once a day by the local
scheduled task (hatchuping_update.py), which also updates the Excel tracker.
"""
import json
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "hatchuping"

C_M2 = "#2a78d6"   # 2편 (blue)
C_M1 = "#eb6834"   # 1편 (orange)

st.set_page_config(page_title="하츄핑2 예고편 트래커", page_icon="🐳", layout="wide")


@st.cache_data(ttl=600, show_spinner=False)
def load():
    dm = pd.read_csv(DATA / "daily_main.csv", parse_dates=["date"])
    dt = pd.read_csv(DATA / "daily_teaser.csv", parse_dates=["date"])
    vel = pd.read_csv(DATA / "velocity.csv", parse_dates=["date"])
    sent = json.loads((DATA / "sentiment.json").read_text(encoding="utf-8"))
    src = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    bk = pd.read_csv(DATA / "booking.csv", parse_dates=["date"])
    bkm = json.loads((DATA / "booking_meta.json").read_text(encoding="utf-8"))
    return dm, dt, vel, sent, src, meta, bk, bkm


def m1_tickets_at(dday, curve):
    """1편's bookings at D-<dday>. Exact point, or geometric interpolation
    between the two nearest observed points (D-8 ~ D-1). None outside range."""
    import math
    pts = sorted(curve, key=lambda p: -p["dday"])          # D-13 → D-1
    for p in pts:
        if p["dday"] == dday:
            return p["tickets"], p.get("kind", "관측")
    if dday > pts[0]["dday"] or dday < pts[-1]["dday"]:
        return None, None
    for a, b in zip(pts, pts[1:]):
        if a["dday"] > dday > b["dday"]:
            f = (a["dday"] - dday) / (a["dday"] - b["dday"])
            v = math.exp(math.log(a["tickets"]) * (1 - f) + math.log(b["tickets"]) * f)
            return round(v), "보간 추정"
    return None, None


def day_axis(dates, max_labels=12):
    """One tick label per real day.

    A plain temporal axis picks tick count from pixel width, so a 3-day span on a
    wide chart repeats the same label ('7/22 7/22 7/22 …'). Pinning the tick
    values to the observed days fixes that; thin them out once there are many.
    """
    ds = pd.to_datetime(pd.Series(list(dates))).dt.normalize().drop_duplicates().sort_values()
    step = max(1, -(-len(ds) // max_labels))
    vals = [d.to_pydatetime() for d in ds.iloc[::step]]
    return alt.Axis(format="%-m/%-d", values=vals, labelAngle=0, labelOverlap=False)


def cum_chart(df, ycol, series_name, benchmark, bench_label, ytitle):
    """Cumulative line vs a 1편 benchmark rule."""
    base = df[["date", ycol]].rename(columns={ycol: "값"})
    line = alt.Chart(base).mark_line(strokeWidth=2.2, point=alt.OverlayMarkDef(size=70),
                                     color=C_M2, interpolate="monotone").encode(
        x=alt.X("date:T", title=None, axis=day_axis(df["date"])),
        y=alt.Y("값:Q", title=ytitle, axis=alt.Axis(format=",.0f")),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("값:Q", title=series_name, format=",.0f")])
    rule_df = pd.DataFrame({"y": [benchmark], "라벨": [bench_label]})
    rule = alt.Chart(rule_df).mark_rule(color=C_M1, strokeDash=[5, 4],
                                        strokeWidth=1.6).encode(
        y="y:Q", tooltip=[alt.Tooltip("라벨:N", title=""),
                          alt.Tooltip("y:Q", title="1편", format=",.0f")])
    text = alt.Chart(rule_df).mark_text(align="left", dx=4, dy=-8, color=C_M1,
                                        fontSize=12).encode(
        y="y:Q", text="라벨:N", x=alt.value(4))
    return (line + rule + text).properties(height=320)


dm, dt, vel, sent, src, meta, bk, bkm = load()
bm = src["benchmarks"]
last, prev = dm.iloc[-1], (dm.iloc[-2] if len(dm) > 1 else dm.iloc[-1])
week = dm.iloc[-8] if len(dm) > 7 else None
open_day = date.fromisoformat(src["theater_open"])
d_to_open = (open_day - last["date"].date()).days

st.title("🐳 사랑의 하츄핑 2 — 예고편 트래커")
st.caption(f"마지막 업데이트: {meta['last_updated']} · 메인 예고편 공개 D+{int(last['day'])} · "
           f"극장 개봉({src['theater_open']})까지 {d_to_open}일 · 1편(운명의 시작)과 비교")

# ================= 1. 메인 예고편
st.header("1. 메인 예고편", divider="blue")

# ---------------- KPI
st.markdown("#### ① 오늘 성적 (2편, 두 채널 합계)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("조회수", f"{last['total_views']:,}", f"{last['total_views']-prev['total_views']:+,} (어제보다)")
c2.metric("좋아요", f"{last['total_likes']:,}", f"{last['total_likes']-prev['total_likes']:+,}")
c3.metric("댓글", f"{last['total_comments']:,}", f"{last['total_comments']-prev['total_comments']:+,}")
c4.metric("1편 전체 대비", f"{last['total_views']/bm['m1_main_views']:.1%}",
          "1편 = 2년 누적 260만 회", delta_color="off")
if week is not None:
    st.caption(f"1주일 전보다: 조회수 {last['total_views']-week['total_views']:+,} · "
               f"댓글 {last['total_comments']-week['total_comments']:+,}")
else:
    st.caption("'1주일 전보다'는 데이터가 7일 이상 쌓이면 표시됩니다.")

colA, colB = st.columns(2)
with colA:
    st.markdown("**메인 예고편 누적 조회수 — 1편 넘어서기**")
    st.altair_chart(cum_chart(dm, "total_views", "2편 합계 조회수",
                              bm["m1_main_views"], f"1편 전체 ({bm['m1_main_views']:,}회)", "조회수"),
                    width="stretch")
with colB:
    st.markdown("**하루에 얼마나 늘었나 (조회수)**")
    d2 = dm.assign(증가=dm["total_views"].diff()).dropna(subset=["증가"])
    # Band (ordinal) x with a fixed step, not a stretched time scale: with only a
    # couple of days a time scale pins the bars to the far left and far right
    # edges. A step keeps each day the same width so the bars stay side by side.
    bar = alt.Chart(d2).mark_bar(color=C_M2, cornerRadiusTopLeft=4,
                                 cornerRadiusTopRight=4, size=26).encode(
        x=alt.X("monthdate(date):O", title=None,
                axis=alt.Axis(format="%-m/%-d", labelAngle=0, labelOverlap="greedy")),
        y=alt.Y("증가:Q", title="증가 조회수", axis=alt.Axis(format=",.0f")),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("증가:Q", format="+,")])
    st.altair_chart(bar.properties(height=320, width=alt.Step(46)), width="content")

# ---------------- velocity
st.markdown("#### ② 댓글 반응 속도")
st.caption("2편은 13일 만에 1편이 2년 동안 모은 댓글 수(321개)를 넘었습니다.")
st.altair_chart(cum_chart(vel, "cum_comments", "2편 누적 댓글",
                          bm["m1_main_comments"], f"1편 전체 ({bm['m1_main_comments']}개)", "댓글 수"),
                width="stretch")

# ---------------- sentiment
st.markdown("#### ③ 댓글 분위기 (5단계 감성 분석)")
tab_main, tab_teaser = st.tabs(["메인 예고편", "티저 예고편"])
for tab, key in [(tab_main, "main"), (tab_teaser, "teaser")]:
    blk = sent[key]
    m1_total, m2_total = sum(blk["m1"]), sum(blk["m2"])
    rows = []
    for i, lab in enumerate(sent["labels"]):
        rows.append({"분류": lab, "영화": blk["m1_name"], "개수": blk["m1"][i], "비율": blk["m1"][i] / m1_total})
        rows.append({"분류": lab, "영화": blk["m2_name"], "개수": blk["m2"][i], "비율": blk["m2"][i] / m2_total})
    sdf = pd.DataFrame(rows)
    with tab:
        ch = alt.Chart(sdf).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("분류:N", sort=sent["labels"], title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("영화:N", sort=[blk["m1_name"], blk["m2_name"]]),
            y=alt.Y("비율:Q", axis=alt.Axis(format=".0%"), title="비율"),
            color=alt.Color("영화:N",
                            scale=alt.Scale(domain=[blk["m1_name"], blk["m2_name"]],
                                            range=[C_M1, C_M2]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["분류:N", "영화:N", alt.Tooltip("개수:Q", format=",.0f"),
                     alt.Tooltip("비율:Q", format=".1%")])
        txt = alt.Chart(sdf).mark_text(dy=-6, fontSize=11).encode(
            x=alt.X("분류:N", sort=sent["labels"]),
            xOffset=alt.XOffset("영화:N", sort=[blk["m1_name"], blk["m2_name"]]),
            y="비율:Q", text="개수:Q", detail="영화:N")
        st.altair_chart((ch + txt).properties(height=300), width="stretch")
        pos1 = (blk["m1"][0] + blk["m1"][1]) / m1_total
        pos2 = (blk["m2"][0] + blk["m2"][1]) / m2_total
        a, b = st.columns(2)
        a.metric(f"긍정 비율 — {blk['m1_name']}", f"{pos1:.1%}", blk["m1_note"], delta_color="off")
        b.metric(f"긍정 비율 — {blk['m2_name']}", f"{pos2:.1%}", blk["m2_note"], delta_color="off")
st.caption("강한 긍정 = '꼭 보러 간다' 같은 관람 의지 · 키워드 자동 분류 (막대 위 숫자 = 실제 댓글 개수)")

# ================= 2. 티저 예고편
st.header("2. 티저 예고편", divider="blue")
st.markdown("#### 2편, 3개 영상 합계")
tl, tp = dt.iloc[-1], (dt.iloc[-2] if len(dt) > 1 else dt.iloc[-1])
c1, c2, c3 = st.columns(3)
c1.metric("티저 조회수", f"{tl['total_views']:,}", f"{tl['total_views']-tp['total_views']:+,} (어제보다)")
c2.metric("티저 댓글", f"{tl['total_comments']:,}")
c3.metric("1편 티저 대비", f"{tl['total_views']/bm['m1_teaser_views']:.1%}",
          "1편 티저 = 6개 영상, 2년 누적", delta_color="off")
st.altair_chart(cum_chart(dt, "total_views", "2편 티저 합계 조회수",
                          bm["m1_teaser_views"], f"1편 티저 전체 ({bm['m1_teaser_views']:,}회)", "조회수"),
                width="stretch")

# ================= 3. 실시간 예매율
st.header("3. 실시간 예매율 — 흥행 예측", divider="blue")
st.caption("매일 KOBIS 실시간 예매율에서 수집 · 1편 비교: 보도 관측 4개 시점(D-8·D-7·D-5·D-1) + "
           "D-13~D-9는 역추정치 (보도 없음, 관측 4점 성장곡선 +23%/일 역외삽)")

bl = bk.iloc[-1]
bp = bk.iloc[-2] if len(bk) > 1 else None
cur_dday = int(bl["dday"])
m1_now, m1_kind = m1_tickets_at(cur_dday, bkm["m1_curve"])

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"오늘 예매관객수 (D-{cur_dday})", f"{int(bl['tickets']):,}명",
          f"{int(bl['tickets'] - bp['tickets']):+,} (어제보다)" if bp is not None else "수집 시작",
          delta_color="normal" if bp is not None else "off")
c2.metric("예매율 · 순위", f"{bl['rate']}% · {int(bl['rank'])}위")
if m1_now:
    pace = bl["tickets"] / m1_now
    c3.metric(f"1편 같은 시점(D-{cur_dday}) 대비", f"{pace:.2f}배",
              f"1편 D-{cur_dday}: {m1_now:,}명 ({m1_kind})", delta_color="off")
    c4.metric("예측 실관객수 (1편 페이스 대비)", f"{pace * bkm['m1_final']:,.0f}명",
              f"= {pace:.2f} × 1편 최종 {bkm['m1_final']:,}명", delta_color="off")
else:
    c3.metric(f"1편 같은 시점(D-{cur_dday}) 대비", "비교 불가",
              "1편 예매 관측은 D-8부터 있음 (7/28부터 비교 시작)", delta_color="off")
    c4.metric("배수 방식 참고 예측", f"{bl['tickets'] * bkm['avg_multiplier']:,.0f}명",
              f"= 지금 예매 × 평균 배수 {bkm['avg_multiplier']}x (D-1 전엔 과소추정)", delta_color="off")

# D-day curve: 2편 line vs 1편 observed points
bk2 = bk.assign(x=-bk["dday"], 영화="2편 (매일 수집)")
m1df = pd.DataFrame(bkm["m1_curve"]).assign(x=lambda d: -d["dday"], 영화="1편 (보도 관측)")
line2 = alt.Chart(bk2).mark_line(strokeWidth=2.2, color=C_M2,
                                 point=alt.OverlayMarkDef(size=70, color=C_M2)).encode(
    x=alt.X("x:Q", title="개봉까지 남은 날", scale=alt.Scale(domain=[-14, 0]),
            axis=alt.Axis(labelExpr="datum.value == 0 ? '개봉일' : 'D-' + -datum.value", values=list(range(-14, 1)))),
    y=alt.Y("tickets:Q", title="예매관객수", axis=alt.Axis(format=",.0f")),
    tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
             alt.Tooltip("dday:Q", title="D-"), alt.Tooltip("tickets:Q", title="예매", format=",.0f")])
line1 = alt.Chart(m1df).mark_line(strokeWidth=1.8, color=C_M1, strokeDash=[5, 4]).encode(
    x="x:Q", y="tickets:Q")
pts1 = alt.Chart(m1df).mark_point(size=80, shape="square", color=C_M1).encode(
    x="x:Q", y="tickets:Q",
    fill=alt.Fill("kind:N", scale=alt.Scale(domain=["관측", "외삽 추정"], range=[C_M1, "transparent"]), legend=None),
    tooltip=[alt.Tooltip("dday:Q", title="1편 D-"),
             alt.Tooltip("tickets:Q", title="1편 예매", format=",.0f"),
             alt.Tooltip("kind:N", title="구분"),
             alt.Tooltip("note:N", title="비고")])
lbl = alt.Chart(pd.DataFrame([
    {"x": -8, "tickets": 18000, "t": "1편"},
])).mark_text(color=C_M1, dy=-12, fontSize=12).encode(x="x:Q", y="tickets:Q", text="t:N")
st.altair_chart((line2 + line1 + pts1 + lbl).properties(height=340), width="stretch")
st.caption(f"⚫ 파란 선 = 2편 (매일 수집) · 🟧 주황 점선 = 1편 (채운 네모 = 보도 관측 4개 시점, "
           f"빈 네모 D-13~D-9 = 보도가 없어 성장곡선으로 역추정) · "
           f"1편 D-1 예매 74,006명 → 최종 {bkm['m1_final']:,}명 (배수 {bkm['m1_multiplier']:.1f}x)")

with st.expander("예측 방법 설명 (간단히)"):
    st.markdown(f"""
- **1편 페이스 대비 (기본)**: 같은 D-day에 2편 예매 ÷ 1편 예매 = 페이스 배수 → 1편 최종 관객수({bkm['m1_final']:,}명)에 곱함.
  예: D-7에 2편이 23,000명, 1편이 22,000명이었다면 → 23,000÷22,000 × {bkm['m1_final']:,} ≈ **1,295,000명**
- **배수 방식**: 개봉 전날(D-1) 예매관객수 × **{bkm['avg_multiplier']}배** (가족 애니메이션 11편 평균).
  D-1 전에 쓰면 작게 나옴 — 8/4 저녁 값이 진짜 예측.
- **회귀식**: log10(최종) = {bkm['regression']['intercept']:.2f} + {bkm['regression']['slope']:.2f}×log10(D-1 예매), R²={bkm['regression']['r2']:.2f}.
- 계산 근거·출처 전부: 하츄핑2_흥행예측.xlsx (로컬)
""")
with st.expander("매일 기록 표 (예매)"):
    st.dataframe(bk.sort_values("date", ascending=False), hide_index=True, width="stretch")

# ================= 4. 언급량 추이 (placeholder)
st.header("4. 언급량 추이", divider="blue")
st.info("준비 중입니다 — 커뮤니티·뉴스·검색 언급량을 모아서 곧 추가할 예정입니다.")

# ---------------- raw data
st.header("원본 데이터", divider="gray")
with st.expander("매일 기록 표 (메인 예고편)"):
    st.dataframe(dm.sort_values("date", ascending=False), hide_index=True, width="stretch")
with st.expander("매일 기록 표 (티저)"):
    st.dataframe(dt.sort_values("date", ascending=False), hide_index=True, width="stretch")
with st.expander("원본 영상 링크 (1편 티저 6개 · 2편 티저 3개 · 메인 4개)"):
    sv = pd.DataFrame(src["videos"])
    sv.columns = ["구분", "채널", "공개일", "댓글", "링크"]
    st.dataframe(sv, hide_index=True, width="stretch",
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="🔗 보기")})
st.caption("데이터: 유튜브 공개 페이지에서 매일 1회 수집 · 엑셀 원본: Hatchuping2 tracker_v1.xlsx (로컬)")

