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
    return dm, dt, vel, sent, src, meta


def cum_chart(df, ycol, series_name, benchmark, bench_label, ytitle):
    """Cumulative line vs a 1편 benchmark rule."""
    base = df[["date", ycol]].rename(columns={ycol: "값"})
    line = alt.Chart(base).mark_line(strokeWidth=2.2, point=alt.OverlayMarkDef(size=70),
                                     color=C_M2, interpolate="monotone").encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%-m/%-d")),
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


dm, dt, vel, sent, src, meta = load()
bm = src["benchmarks"]
last, prev = dm.iloc[-1], (dm.iloc[-2] if len(dm) > 1 else dm.iloc[-1])
week = dm.iloc[-8] if len(dm) > 7 else None
open_day = date.fromisoformat(src["theater_open"])
d_to_open = (open_day - last["date"].date()).days

st.title("🐳 사랑의 하츄핑 2 — 예고편 트래커")
st.caption(f"마지막 업데이트: {meta['last_updated']} · 메인 예고편 공개 D+{int(last['day'])} · "
           f"극장 개봉({src['theater_open']})까지 {d_to_open}일 · 1편(운명의 시작)과 비교")

# ---------------- KPI
st.markdown("#### ① 메인 예고편 오늘 성적 (2편, 두 채널 합계)")
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
    bar = alt.Chart(d2).mark_bar(color=C_M2, cornerRadiusTopLeft=4,
                                 cornerRadiusTopRight=4, size=26).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%-m/%-d")),
        y=alt.Y("증가:Q", title="증가 조회수", axis=alt.Axis(format=",.0f")),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("증가:Q", format="+,")])
    st.altair_chart(bar.properties(height=320), width="stretch")

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

# ---------------- teaser
st.markdown("#### ④ 티저 예고편 (2편, 3개 영상 합계)")
tl, tp = dt.iloc[-1], (dt.iloc[-2] if len(dt) > 1 else dt.iloc[-1])
c1, c2, c3 = st.columns(3)
c1.metric("티저 조회수", f"{tl['total_views']:,}", f"{tl['total_views']-tp['total_views']:+,} (어제보다)")
c2.metric("티저 댓글", f"{tl['total_comments']:,}")
c3.metric("1편 티저 대비", f"{tl['total_views']/bm['m1_teaser_views']:.1%}",
          "1편 티저 = 6개 영상, 2년 누적", delta_color="off")
st.altair_chart(cum_chart(dt, "total_views", "2편 티저 합계 조회수",
                          bm["m1_teaser_views"], f"1편 티저 전체 ({bm['m1_teaser_views']:,}회)", "조회수"),
                width="stretch")

# ---------------- raw data
st.markdown("#### ⑤ 원본 데이터")
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

