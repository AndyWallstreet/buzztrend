# -*- coding: utf-8 -*-
# v2026-08-04b: section 5 스크린 캐파 added
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


# stamp = load()가 읽는 파일 전부의 수정 시각 — 하나라도 바뀌면 캐시 키가 바뀌어
# 바로 새로 읽는다. (고정 ttl이면 업데이트 직후에도 최대 10분간 옛날 숫자가 보였음)
# meta.json 하나만 보던 때는, 예매 파일만 고친 날 화면이 옛날 숫자에 그대로 멈춰 있었다 —
# git은 mtime을 보존하지 않아서 서버에선 '바뀐 파일'만 새 mtime을 받기 때문.
LOAD_FILES = ("daily_main.csv", "daily_teaser.csv", "velocity.csv", "sentiment.json",
              "sources.json", "meta.json", "booking.csv", "booking_meta.json",
              "booking_now.json")


def load_stamp():
    return tuple(round((DATA / f).stat().st_mtime, 3) if (DATA / f).exists() else 0.0
                 for f in LOAD_FILES)


@st.cache_data(show_spinner=False)
def load(stamp):
    dm = pd.read_csv(DATA / "daily_main.csv", parse_dates=["date"])
    dt = pd.read_csv(DATA / "daily_teaser.csv", parse_dates=["date"])
    vel = pd.read_csv(DATA / "velocity.csv", parse_dates=["date"])
    sent = json.loads((DATA / "sentiment.json").read_text(encoding="utf-8"))
    src = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    bk = pd.read_csv(DATA / "booking.csv", parse_dates=["date"])
    bkm = json.loads((DATA / "booking_meta.json").read_text(encoding="utf-8"))
    # 마지막 수집 순간의 '지금 실제 숫자' — 없을 수도 있으니 있으면만 쓴다
    nowp = DATA / "booking_now.json"
    bnow = json.loads(nowp.read_text(encoding="utf-8")) if nowp.exists() else None
    return dm, dt, vel, sent, src, meta, bk, bkm, bnow


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


def fmt_ts(ts):
    """'2026-08-04 07:17' → '오전 7:17'.

    맨 숫자만 '07:17'로 내놓으면 보는 사람이 무슨 시각인지 알 수 없다 —
    오전/오후를 붙이고, 부르는 쪽에서 '데이터 수집' 같은 라벨을 앞에 단다."""
    d = pd.Timestamp(ts)
    return f"{'오전' if d.hour < 12 else '오후'} {d.hour % 12 or 12}:{d.minute:02d}"


FUTURE_DAYS = 14   # 앞으로 2주치 자리를 미리 비워 둔다 (개봉일까지 남은 길이가 보이도록)


def date_span(dates, extra_days=FUTURE_DAYS):
    """Observed days plus a run of empty future days, one entry per day."""
    ds = pd.to_datetime(pd.Series(list(dates))).dt.normalize()
    return pd.date_range(ds.min(), ds.max() + pd.Timedelta(days=extra_days), freq="D")


def day_axis(days, max_labels=12):
    """One tick label per day, thinned out once there are many.

    A plain temporal axis picks its tick count from pixel width, so a short span
    on a wide chart repeats the same label ('7/22 7/22 7/22 …'). Pinning the tick
    values to real days fixes that.
    """
    days = pd.DatetimeIndex(days)
    step = max(1, -(-len(days) // max_labels))
    return alt.Axis(format="%-m/%-d", values=[d.to_pydatetime() for d in days[::step]],
                    labelAngle=0, labelOverlap=False)


def _dt(ts):
    return alt.DateTime(year=ts.year, month=ts.month, date=ts.day)


def open_rule(open_day, y_field="값"):
    """Dashed marker on 개봉일 so the empty future space reads as a countdown."""
    odf = pd.DataFrame({"x": [pd.Timestamp(open_day)], "t": ["개봉"]})
    line = alt.Chart(odf).mark_rule(color="#8a8f98", strokeDash=[3, 3],
                                    strokeWidth=1.2).encode(x="x:T")
    lab = alt.Chart(odf).mark_text(color="#8a8f98", fontSize=11, align="left",
                                   dx=4, baseline="top").encode(
        x="x:T", y=alt.value(4), text="t:N")
    return line + lab


def cum_chart(df, ycol, series_name, benchmark, bench_label, ytitle, open_day=None):
    """Cumulative line vs a 1편 benchmark rule, with room left for future days."""
    base = df[["date", ycol]].rename(columns={ycol: "값"})
    span = date_span(df["date"])
    line = alt.Chart(base).mark_line(strokeWidth=2.2, point=alt.OverlayMarkDef(size=70),
                                     color=C_M2, interpolate="monotone").encode(
        x=alt.X("date:T", title=None, axis=day_axis(span),
                scale=alt.Scale(domain=[_dt(span[0]), _dt(span[-1])])),
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
    layers = [line, rule, text]
    if open_day is not None:
        layers.append(open_rule(open_day))
    return alt.layer(*layers).properties(height=320)


dm, dt, vel, sent, src, meta, bk, bkm, bnow = load(load_stamp())
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
                              bm["m1_main_views"], f"1편 전체 ({bm['m1_main_views']:,}회)", "조회수",
                              open_day=open_day),
                    width="stretch")
with colB:
    st.markdown("**하루에 얼마나 늘었나 (조회수)**")
    # diff() subtracts the previous ROW, so a skipped tracking day would pile two
    # days of growth onto one bar and leave a hole next to it. Spread each gain over
    # the days it actually covers instead — the straight line between the two real
    # snapshots, no invented numbers. Multi-day bars are flagged as such.
    d2 = dm[["date", "total_views"]].copy()
    d2["증가"] = d2["total_views"].diff()
    d2["간격"] = d2["date"].diff().dt.days
    d2 = d2.dropna(subset=["증가"])
    spread = []
    for _, r in d2.iterrows():
        n = max(1, int(r["간격"]))
        for k in range(n):
            spread.append({"date": r["date"] - pd.Timedelta(days=n - 1 - k),
                           "증가": r["증가"] / n,
                           "구분": "관측" if n == 1 else f"{n}일 평균",
                           "단일": n == 1})
    d2 = pd.DataFrame(spread)
    # Band (ordinal) x, not a stretched time scale: a time scale pins two bars to
    # the far left and far right edges. Reindexing over the padded span gives every
    # future day its own empty band, so bars stay side by side on the left and the
    # remaining days to 개봉 are visible as blank slots.
    span = date_span(d2["date"])
    d2 = d2.set_index("date").reindex(span).rename_axis("date").reset_index()
    d2["구분"] = d2["구분"].fillna("관측")
    d2["단일"] = d2["단일"].fillna(True).astype(bool)
    # Band positions are plain day labels: an ordinal axis matches tick values as
    # strings, so datetimes there would silently drop every label.
    d2["일자"] = [f"{d.month}/{d.day}" for d in d2["date"]]
    order = list(d2["일자"])
    bar = alt.Chart(d2).mark_bar(color=C_M2, cornerRadiusTopLeft=4,
                                 cornerRadiusTopRight=4).encode(
        x=alt.X("일자:O", title=None, sort=order, scale=alt.Scale(paddingInner=0.35),
                axis=alt.Axis(labelAngle=0, labelOverlap=False, values=order[::2])),
        y=alt.Y("증가:Q", title="증가 조회수", axis=alt.Axis(format=",.0f")),
        opacity=alt.Opacity("단일:N", scale=alt.Scale(domain=[True, False],
                                                    range=[1.0, 0.5]), legend=None),
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("증가:Q", format="+,"),
                 alt.Tooltip("구분:N", title="구분")])
    st.altair_chart(bar.properties(height=320), width="stretch")

# ---------------- velocity
st.markdown("#### ② 댓글 반응 속도")
st.caption("2편은 13일 만에 1편이 2년 동안 모은 댓글 수(321개)를 넘었습니다.")
st.altair_chart(cum_chart(vel, "cum_comments", "2편 누적 댓글",
                          bm["m1_main_comments"], f"1편 전체 ({bm['m1_main_comments']}개)", "댓글 수",
                          open_day=open_day),
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
                          bm["m1_teaser_views"], f"1편 티저 전체 ({bm['m1_teaser_views']:,}회)", "조회수",
                          open_day=open_day),
                width="stretch")

# ================= 3. 실시간 예매율
st.header("3. 실시간 예매율 — 흥행 예측", divider="blue")
st.caption("매일 KOBIS 실시간 예매율에서 수집 · 1편 비교: 보도 관측 4개 시점(D-8·D-7·D-5·D-1) + "
           "D-13~D-9는 역추정치 (보도 없음, 관측 4점 성장곡선 +23%/일 역외삽)")

# KOBIS 아침 수집값은 '어제까지의 누적'이라서: 마지막 확정/저녁까지 행 = 어제,
# kind='추정' 행 = 오늘(어제 속도로 오른다고 가정한 값)
bk["kind"] = bk["kind"].fillna("확정")
solid = bk[bk["kind"] != "추정"]          # 실제 수집값 (어제까지)
estdf = bk[bk["kind"] == "추정"]          # 오늘 추정
bl = solid.iloc[-1]                        # 어제 (마지막 실측)
bp = solid.iloc[-2] if len(solid) > 1 else None
y_dday = int(bl["dday"])
m1_y, m1_y_kind = m1_tickets_at(y_dday, bkm["m1_curve"])

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"어제까지 예매관객수 (D-{y_dday} {bl['kind']})", f"{int(bl['tickets']):,}명",
          f"{int(bl['tickets'] - bp['tickets']):+,} (그제보다)" if bp is not None else "수집 시작",
          delta_color="normal" if bp is not None else "off")
if len(estdf):
    be = estdf.iloc[-1]
    live = bnow if (bnow and bnow.get("date") == str(be["date"].date())) else None
    c2.metric(f"오늘 마감 추정 (D-{int(be['dday'])})", f"{int(be['tickets']):,}명",
              (f"데이터 수집 {fmt_ts(live['ts'])} 기준 {live['tickets']:,}명 → 마감 환산"
               if live else "어제 증가분만큼 오른다고 가정"), delta_color="off")
else:
    c2.metric("예매율 · 순위", f"{bl['rate']}% · {int(bl['rank'])}위")
if m1_y:
    pace = bl["tickets"] / m1_y
    c3.metric(f"1편 같은 시점(D-{y_dday}) 대비", f"{pace:.2f}배",
              f"1편 D-{y_dday}: {m1_y:,}명 ({m1_y_kind})", delta_color="off")
    c4.metric("예측 실관객수 (1편 페이스 대비)", f"{pace * bkm['m1_final']:,.0f}명",
              f"= {pace:.2f} × 1편 최종 {bkm['m1_final']:,}명", delta_color="off")
else:
    c3.metric(f"1편 같은 시점(D-{y_dday}) 대비", "비교 불가",
              "1편 예매 관측은 D-8부터 있음 (7/28부터 비교 시작)", delta_color="off")
    c4.metric("배수 방식 참고 예측", f"{bl['tickets'] * bkm['avg_multiplier']:,.0f}명",
              f"= 지금 예매 × 평균 배수 {bkm['avg_multiplier']}x (D-1 전엔 과소추정)", delta_color="off")
st.caption(
    (f"📍 데이터 수집 {fmt_ts(bnow['ts'])} 기준 — 예매율 {bnow['rate']}% · {int(bnow['rank'])}위 · "
     f"실제 {bnow['tickets']:,}명 · "
     if bnow else "")
    + f"어제 마감 {bl['rate']}% · {int(bl['rank'])}위 · "
      "아침에 수집한 KOBIS 숫자는 어제까지의 값이라 어제 자리에 기록하고, 오늘은 추정으로 표시")

# D-day curve: 2편 line vs 1편 observed points
bk2 = bk.assign(x=-bk["dday"], 영화="2편 (매일 수집)")
# 같은 D-day의 1편 값을 옆에 붙여 둔다 — 점 하나만 올려도 2편/1편/배수가 같이 보이도록
bk2["m1_same"] = [m1_tickets_at(int(d), bkm["m1_curve"])[0] for d in bk2["dday"]]
bk2["배수"] = bk2.apply(
    lambda r: round(r["tickets"] / r["m1_same"], 2) if pd.notna(r["m1_same"]) else None, axis=1)
TIP2 = [alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
        alt.Tooltip("dday:Q", title="D-"),
        alt.Tooltip("tickets:Q", title="2편 예매", format=",.0f"),
        alt.Tooltip("kind:N", title="구분"),
        alt.Tooltip("m1_same:Q", title="1편 같은 날", format=",.0f"),
        alt.Tooltip("배수:Q", title="1편 대비(배)", format=".2f")]

solid2 = bk2[bk2["kind"] != "추정"]                    # 실측 — 실선 + 채운 점
est2 = bk2[bk2["kind"] == "추정"]
# 추정 구간: 마지막 실측점 → 추정점을 점선으로 잇는다
dash2 = pd.concat([solid2.tail(1), est2]) if len(est2) else est2.iloc[0:0]

m1df = pd.DataFrame(bkm["m1_curve"]).assign(x=lambda d: -d["dday"], 영화="1편 (보도 관측)")
line2 = alt.Chart(solid2).mark_line(strokeWidth=2.2, color=C_M2,
                                    point=alt.OverlayMarkDef(size=90, color=C_M2)).encode(
    x=alt.X("x:Q", title="개봉까지 남은 날", scale=alt.Scale(domain=[-14, 0]),
            axis=alt.Axis(labelExpr="datum.value == 0 ? '개봉일' : 'D-' + -datum.value", values=list(range(-14, 1)))),
    y=alt.Y("tickets:Q", title="예매관객수", axis=alt.Axis(format=",.0f")),
    tooltip=TIP2)
# 오늘 추정: 점선 + 속이 빈 원 (실측과 헷갈리지 않게)
lineE = alt.Chart(dash2).mark_line(strokeWidth=2, color=C_M2, strokeDash=[3, 4]).encode(
    x="x:Q", y="tickets:Q")
ptsE = alt.Chart(est2).mark_point(size=110, color=C_M2, fill="transparent",
                                  strokeWidth=2.2).encode(
    x="x:Q", y="tickets:Q", tooltip=TIP2)
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
# 2편 점은 8px밖에 안 돼서 1편 네모(바로 6px 아래, 위에 그려짐)에 가려 마우스가 잘 안 닿았다.
# 투명한 큰 원을 맨 위에 깔아 2편 툴팁이 항상 먼저 잡히게 한다.
hover2 = alt.Chart(bk2).mark_point(size=400, opacity=0).encode(
    x="x:Q", y="tickets:Q", tooltip=TIP2)

# 지금 이 순간 실제로 KOBIS에 찍혀 있는 값 — 추정(빈 원)과 구분되게 채운 마름모로.
# 실측이지만 '하루 마감치'가 아니라 '진행 중' 값이라 파란 실선에는 넣지 않는다.
layers = [line2, lineE, ptsE, line1, pts1, lbl, hover2]
if bnow:
    nowdf = pd.DataFrame([{
        "x": -bnow["dday"], "tickets": bnow["tickets"], "ts": bnow["ts"],
        "rate": bnow.get("rate"), "rank": bnow.get("rank"),
        "m1_same": m1_tickets_at(int(bnow["dday"]), bkm["m1_curve"])[0],
        "est_close": bnow.get("est_close")}])
    nowdf["배수"] = nowdf.apply(
        lambda r: round(r["tickets"] / r["m1_same"], 2) if pd.notna(r["m1_same"]) else None, axis=1)
    TIPN = [alt.Tooltip("ts:N", title="수집 시각"),
            alt.Tooltip("tickets:Q", title="지금 예매", format=",.0f"),
            alt.Tooltip("est_close:Q", title="오늘 마감 추정", format=",.0f"),
            alt.Tooltip("rate:Q", title="예매율(%)"),
            alt.Tooltip("rank:Q", title="순위"),
            alt.Tooltip("m1_same:Q", title="1편 같은 날", format=",.0f"),
            alt.Tooltip("배수:Q", title="1편 대비(배)", format=".2f")]
    ptsN = alt.Chart(nowdf).mark_point(shape="diamond", size=150, color=C_M2,
                                       filled=True, opacity=1).encode(
        x="x:Q", y="tickets:Q", tooltip=TIPN)
    lblN = alt.Chart(nowdf.assign(label="데이터 수집 " + fmt_ts(bnow["ts"]))).mark_text(
        color=C_M2, dy=16, fontSize=11).encode(x="x:Q", y="tickets:Q", text="label:N")
    layers += [ptsN, lblN]
st.altair_chart(alt.layer(*layers).properties(height=340), width="stretch")
st.caption(f"⚫ 파란 실선 = 2편 실측 (하루 마감 기준, 다음날 아침 수집) · "
           f"🔷 파란 마름모 = 지금 이 순간 KOBIS 실제 값 (진행 중) · 빈 파란 원 = 오늘 마감 추정 · "
           f"🟧 주황 점선 = 1편 (채운 네모 = 보도 관측 4개 시점, "
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

# ================= 4. 언급량 추이
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

# ================= 5. 스크린 캐파
st.header("5. 스크린수 비교", divider="blue")
scr_path = DATA / "screens.json"
if not scr_path.exists():
    st.info("준비 중입니다 — 스크린 수 데이터를 곧 추가할 예정입니다.")
else:
    scr = json.loads(scr_path.read_text(encoding="utf-8"))
    m1o, m1p = scr["m1"]["open_day"], scr["m1"]["peak_day"]
    tgt, m1f = scr["target"], scr["m1"]["final_admissions"]
    seats = scr["seats_per_show"]
    pv = scr["m2_preview"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2편 개봉 스크린 (확정)", f"{scr['m2']['screens']:,}개",
              f"{scr['m2']['screens'] - m1o['screens']:+,}개 (1편 개봉일보다)")
    c2.metric("1편 개봉일 스크린", f"{m1o['screens']:,}개",
              f"하루 {m1o['shows']:,}회 상영", delta_color="off")
    c3.metric("1편 최대 스크린", f"{m1p['screens']:,}개",
              f"첫 토요일, 하루 {m1p['admissions']:,}명", delta_color="off")
    c4.metric("목표 대비 1편 최종", f"{m1f / tgt:.0%}",
              f"1편 {m1f:,}명 ÷ 목표 {tgt:,}명", delta_color="off")
    st.caption(f"2편 {scr['m2']['screens']:,}개 = 전국 {scr['m2']['theaters']:,}개 영화관, "
               f"1편 최대({m1p['screens']:,}개)와 같은 수준 · {scr['m2']['note']} · "
               f"개봉 전 유료 시사(8/1~8/3)는 {pv['screens']}개 스크린에서 {pv['admissions']:,}명")

    colL, colR = st.columns(2)
    with colL:
        st.markdown("**스크린 수 비교**")
        sc_df = pd.DataFrame([
            {"구분": pv["label"], "스크린": pv["screens"], "영화": "2편"},
            {"구분": m1o["label"], "스크린": m1o["screens"], "영화": "1편"},
            {"구분": "2편 개봉 (확정)", "스크린": scr["m2"]["screens"], "영화": "2편"},
            {"구분": m1p["label"], "스크린": m1p["screens"], "영화": "1편"},
        ])
        sc_bar = alt.Chart(sc_df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                                           size=45).encode(
            x=alt.X("구분:N", sort=list(sc_df["구분"]), title=None,
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("스크린:Q", title="스크린 수", axis=alt.Axis(format=",.0f")),
            color=alt.Color("영화:N",
                            scale=alt.Scale(domain=["1편", "2편"], range=[C_M1, C_M2]),
                            legend=None),
            tooltip=["구분:N", alt.Tooltip("스크린:Q", format=",.0f")])
        sc_txt = alt.Chart(sc_df).mark_text(dy=-8, fontSize=12).encode(
            x=alt.X("구분:N", sort=list(sc_df["구분"])), y="스크린:Q",
            text=alt.Text("스크린:Q", format=","))
        st.altair_chart((sc_bar + sc_txt).properties(height=300), width="stretch")
    with colR:
        st.markdown("**좌석은 충분한가 — 간단 계산**")
        day_seats = m1p["shows"] * seats
        per_show = m1p["admissions"] / m1p["shows"]
        st.markdown(f"""
| | |
|---|---|
| 2편 개봉 스크린 (확정) | **{scr['m2']['screens']:,}개** — 1편 최대({m1p['screens']:,}개)와 같은 수준 |
| 이 규모의 하루 좌석 공급 | {m1p['shows']:,}회 × 약 {seats}석 ≈ **{day_seats:,.0f}석/하루** |
| 목표 {tgt:,}명을 좌석으로 채우면 | {tgt:,} ÷ {day_seats:,.0f} ≈ **{tgt / day_seats:.1f}일치** 좌석 |
| 1편이 실제로 채운 정도 | 회당 평균 {per_show:.0f}명 = 좌석의 약 **{per_show / seats:.0%}** |
| 그 결과 1편 최종 관객 | **{m1f:,}명** |
| 목표 {tgt / 10000:,.0f}만 명에 필요한 흥행력 | 1편의 **{tgt / m1f:.2f}배** |
""")
        st.caption(f"회당 좌석 수 약 {seats}석은 일반 상영관 평균 가정, 상영횟수는 1편 최대일 기준 · "
                   "결론: 좌석 공급은 목표를 넉넉히 감당 — "
                   "관건은 좌석을 얼마나 채우느냐(흥행력)입니다.")

    with st.expander(f"2편 개봉 스크린 {scr['m2']['screens']:,}개 — 체인별 내역 (KOBIS 상영현황정보)"):
        ch_df = pd.DataFrame(scr["m2_chains"])
        st.dataframe(ch_df, hide_index=True, width="stretch")
    with st.expander("2편 유료 시사 (8/1~8/3) — 지역별 스크린 (KOBIS 지역별 통계정보)"):
        rg = pd.DataFrame(scr["m2_regional_preview"])
        st.dataframe(rg.sort_values("스크린수", ascending=False), hide_index=True,
                     width="stretch")
    KOBIS_DAILY = ("https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"
                   "?loadEnd=0&searchType=search&sSearchFrom={d}&sSearchTo={d}")
    st.caption(f"데이터 기준일: {scr['as_of']} · 1편 스크린 수 직접 확인 (KOBIS 일별 박스오피스, "
               f"표의 '사랑의 하츄핑' 행 → 스크린수 열): "
               f"[개봉일 2024-08-07 = 1,065개]({KOBIS_DAILY.format(d='2024-08-07')}) · "
               f"[최대 2024-08-10 = 1,153개]({KOBIS_DAILY.format(d='2024-08-10')}) · "
               "개봉 후에는 실제 일별 스크린 수로 업데이트합니다")

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

