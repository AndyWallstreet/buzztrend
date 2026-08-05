# -*- coding: utf-8 -*-
# v2026-08-04b: section 5 스크린 캐파 added
"""하츄핑 2 예고편 트래커 — 유튜브 성적을 매일 추적, 1편과 비교.

Data files in data/hatchuping/ are refreshed once a day by the local
scheduled task (hatchuping_update.py), which also updates the Excel tracker.
"""
import json
from datetime import date, datetime, timedelta, timezone
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
              "booking_now.json", "m1_daily.csv", "m2_daily.csv", "boxoffice_now.json",
              "ratings.csv", "sentiment_daily.csv", "ratings_peers.json")


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
    # 개봉 후 일별 관객수 (boxoffice_update.py) — 개봉 전엔 아직 없다
    def _bo(name):
        p = DATA / name
        return pd.read_csv(p, parse_dates=["date"]) if p.exists() else None
    m1d, m2d = _bo("m1_daily.csv"), _bo("m2_daily.csv")
    bop = DATA / "boxoffice_now.json"
    bonow = json.loads(bop.read_text(encoding="utf-8")) if bop.exists() else None
    # 실관람객 평점 (ratings_update.py)
    rat, sd = _bo("ratings.csv"), _bo("sentiment_daily.csv")
    pp = DATA / "ratings_peers.json"
    peer = json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else None
    return dm, dt, vel, sent, src, meta, bk, bkm, bnow, m1d, m2d, bonow, rat, sd, peer


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


def forecast_candidates(tickets, dday, bkm):
    """최종 관객수 추정치를 세 가지 방법으로 낸다 — 화면엔 그중 가장 낮은 값만 쓴다.

    D-1처럼 세 방법이 다 살아 있는 날은 값이 2~3% 벌어지는데, 개봉 전 예측을
    높게 불러 두면 나중에 실제보다 부풀려 보이므로 가장 보수적인 쪽을 택한다.
    """
    import math

    out = {}
    m1_t, _ = m1_tickets_at(dday, bkm["m1_curve"])
    if m1_t:
        out["1편 페이스"] = tickets / m1_t * bkm["m1_final"]
    reg = bkm.get("regression") or {}
    if reg.get("slope") and tickets > 0:
        out["회귀분석"] = 10 ** (reg["intercept"] + reg["slope"] * math.log10(tickets))
    if bkm.get("avg_multiplier"):
        out["평균배수"] = tickets * bkm["avg_multiplier"]
    return out


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


dm, dt, vel, sent, src, meta, bk, bkm, bnow, m1d, m2d, bonow, rat, sd, peer = load(load_stamp())
bm = src["benchmarks"]
last, prev = dm.iloc[-1], (dm.iloc[-2] if len(dm) > 1 else dm.iloc[-1])
week = dm.iloc[-8] if len(dm) > 7 else None
open_day = date.fromisoformat(src["theater_open"])
d_to_open = (open_day - last["date"].date()).days

# 개봉 전엔 카운트다운, 개봉 후엔 며칠째인지. 데이터 마지막 행 날짜로 재면 아침 수집분이
# 어제 자로 기록되는 탓에 개봉 당일에도 '개봉까지 1일'이 떠서, 실제 오늘(KST)로 잰다.
_today_kst = datetime.now(timezone(timedelta(hours=9))).date()
_since_open = (_today_kst - open_day).days
open_label = (f"극장 개봉({src['theater_open']})까지 {d_to_open}일" if _since_open < 0
              else f"극장 개봉 D+{_since_open} ({src['theater_open']} 개봉)")

st.title("🐳 사랑의 하츄핑 2 — 예고편 트래커")
st.caption(f"마지막 업데이트: {meta['last_updated']} · 메인 예고편 공개 D+{int(last['day'])} · "
           f"{open_label} · 1편(운명의 시작)과 비교")

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
st.header("3. 개봉 후 실관객수 — 흥행 판정", divider="blue")
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

    # ---- 누적 곡선 비교 (같은 일차끼리)
    span = max(int(m2d["day"].max()) + 7, 14)
    a = m2d[["day", "cum", "adm", "screens"]].copy()
    a["구분"] = "2편"
    b = m1d[m1d["day"] <= span][["day", "cum", "adm", "screens"]].copy()
    b["구분"] = "1편"
    comp = pd.concat([a, b], ignore_index=True)

    base = alt.Chart(comp).encode(
        x=alt.X("day:Q", title="개봉 후 경과일 (0 = 개봉일)",
                scale=alt.Scale(domain=[0, span], nice=False)),
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

    # ---- 공급(스크린)과 수요(좌석점유율)
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("**스크린수 — 공급이 줄면 관객도 준다**")
        sc = alt.Chart(comp).mark_line(point=True).encode(
            x=alt.X("day:Q", title="경과일", scale=alt.Scale(domain=[0, span], nice=False)),
            y=alt.Y("screens:Q", title="스크린수"),
            color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                     range=[C_M2, C_M1]), legend=None),
            strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                               range=[[1, 0], [5, 4]]), legend=None))
        st.altair_chart(sc.properties(height=220), width="stretch")
    with s2:
        st.markdown("**좌석점유율 — 수요의 질 (관객 ÷ 상영횟수×160석)**")
        sr = m2d.copy()
        sr["seat_rate"] = pd.to_numeric(sr["seat_rate"], errors="coerce")
        srm = m1d[m1d["day"] <= span].copy()
        srm["seat_rate"] = pd.to_numeric(srm["seat_rate"], errors="coerce")
        sr["구분"], srm["구분"] = "2편", "1편"
        sd = pd.concat([sr[["day", "seat_rate", "구분"]],
                        srm[["day", "seat_rate", "구분"]]], ignore_index=True)
        ch = alt.Chart(sd).mark_line(point=True).encode(
            x=alt.X("day:Q", title="경과일", scale=alt.Scale(domain=[0, span], nice=False)),
            y=alt.Y("seat_rate:Q", title="좌석점유율", axis=alt.Axis(format=".0%")),
            color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                     range=[C_M2, C_M1]), legend=None),
            strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                               range=[[1, 0], [5, 4]]), legend=None))
        st.altair_chart(ch.properties(height=220), width="stretch")

    st.caption("판단 기준선 — **124만** 넘으면 1편 초과(기본 성공) · **200만** = 예매가 약속한 수준 "
               "(D-1 예매 1.62배) · **250만** = 회귀 상단. 1편은 첫 주말(개봉 4일차)까지 "
               "누적 406,384명으로 최종의 32.8%를 벌었습니다 — 즉 첫 주말 누적 × 약 3.05 ≈ 최종.")

st.divider()
st.header("4. 실관람객 평점 & 반응", divider="blue")
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
st.header("5. 개봉 전 예매율 (기록) — 흥행 예측", divider="blue")
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
    # 예측은 '어제 확정'이 아니라 '오늘 마감 추정' 기준 — 하루 최신이고, D-1엔
    # 1편도 관측값(74,006)이라 보간 없이 같은 시점끼리 비교된다.
    fc_t, fc_d = (int(be["tickets"]), int(be["dday"])) if len(estdf) else (int(bl["tickets"]), y_dday)
    cands = forecast_candidates(fc_t, fc_d, bkm)
    # 1편 페이스법 — 어제 '확정' 예매량의 1편 대비 배수 × 1편 최종 관객수.
    # 추정치가 아닌 확정치에서 나오므로 후보 중 가장 믿을 만한 축이다.
    cands["1편 페이스"] = pace * bkm["m1_final"]
    if cands:
        low = min(cands, key=cands.get)
        basis = (f"= {pace:.2f}배 × 1편 최종 {bkm['m1_final']:,}명"
                 if low == "1편 페이스" else f"= D-{fc_d} {fc_t:,}명 기준 · {low}법")
        c4.metric("예측 실관객수 (보수적)", f"{cands[low]:,.0f}명",
                  f"{basis} (최대 {max(cands.values()):,.0f}명)", delta_color="off")
    else:
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
st.header("6. 언급량 추이", divider="blue")
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
st.header("7. 스크린수 비교", divider="blue")
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

