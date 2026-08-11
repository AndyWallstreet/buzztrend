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
              "board_daily.csv", "board_samples.json",
              "m1_market.csv", "m2_market.csv", "m2_chains.csv", "m1_chains.csv")


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
            _csv("board_daily.csv"), _json("board_samples.json"),
            _csv("m1_market.csv"), _csv("m2_market.csv"), _csv("m2_chains.csv"),
            _csv("m1_chains.csv"))


def date_span(dates, extra_days=3):
    ds = pd.to_datetime(pd.Series(list(dates))).dt.normalize()
    return pd.date_range(ds.min(), ds.max() + pd.Timedelta(days=extra_days), freq="D")


def day_axis(days, max_labels=12):
    """실측 날짜에 눈금을 고정 — 짧은 구간을 넓은 차트에 그리면 같은 라벨이 반복돼서."""
    days = pd.DatetimeIndex(days)
    step = max(1, -(-len(days) // max_labels))
    return alt.Axis(format="%-m/%-d", values=[d.to_pydatetime() for d in days[::step]],
                    labelAngle=0, labelOverlap=False)


WK_COLOR = "#f5c542"


def weekend_band(hi, lo=0, opacity=0.12, x_title=None):
    """경과일(또는 D-day) 축에 주말(토·일) 음영.

    1편(2024-08-07)·2편(2026-08-05) 둘 다 **수요일 개봉**이라 경과일 3·4가 토·일로
    정확히 겹친다 — 같은 축에 한 번만 칠하면 두 편의 주말이 동시에 표시된다.
    D-day 축처럼 lo 가 음수여도 같은 규칙(7의 배수 + 3·4)이 그대로 이어진다.

    x_title 은 함께 겹칠 선 차트의 축 제목과 같은 값을 넘겨야 한다 — Altair 는
    레이어의 x 인코딩을 병합하면서 title=None 이 이기기 때문에, 안 맞추면
    "경과일" 같은 축 제목이 음영을 깐 순간 사라진다.
    """
    lo, hi = float(lo), float(hi)
    rows, w = [], int((lo - 4.5) // 7)
    while 7 * w + 2.5 < hi:
        x0, x1 = max(7 * w + 2.5, lo), min(7 * w + 4.5, hi)
        if x1 > x0:
            rows.append({"x0": x0, "x1": x1})
        w += 1
    return alt.Chart(pd.DataFrame(rows, columns=["x0", "x1"])).mark_rect(
        color=WK_COLOR, opacity=opacity).encode(
        x=alt.X("x0:Q", scale=alt.Scale(domain=[lo, hi], nice=False), title=x_title),
        x2="x1:Q")


def weekend_band_dates(dates, opacity=0.12):
    """날짜(date:T) 축 차트용 주말 음영 — 하루를 ±12시간으로 잡아 그 날에 딱 걸친다."""
    ds = pd.DatetimeIndex(pd.to_datetime(pd.Series(list(dates))).dt.normalize().unique())
    rows = []
    if len(ds):
        rows = [{"x0": d - pd.Timedelta(hours=12), "x1": d + pd.Timedelta(hours=12)}
                for d in pd.date_range(ds.min(), ds.max(), freq="D") if d.dayofweek >= 5]
    return alt.Chart(pd.DataFrame(rows, columns=["x0", "x1"])).mark_rect(
        color=WK_COLOR, opacity=opacity).encode(x="x0:T", x2="x1:T")


m1d, m2d, bonow, rat, sd, peer, bd, bsamp, mk1, mk2, chn, chn1 = load(load_stamp())

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
    m1_last_day = int(m1d["day"].max())

    # 보기 범위 — 기본은 2편이 실제로 지나온 구간(+1주)만 본다. '전체보기'는 1편이
    # 극장에서 내려갈 때까지 전 기간을 펴서, 2편이 지금 어디쯤인지와 앞으로 남은
    # 길이를 한 화면에 보여준다.
    _v1, _v2 = st.columns([1, 2])
    view_all = _v1.radio(
        "보기 범위", [f"최근 (D+0 ~ D+{span})", f"전체보기 (1편 상영 전 기간 D+{m1_last_day})"],
        horizontal=False, index=0, key="bo_view_range",
    ).startswith("전체")
    vspan = m1_last_day if view_all else span
    _v2.caption("**전체보기**를 켜면 1편이 극장에서 완전히 내려갈 때까지"
                f" **{m1_last_day + 1}일 전체**가 펴집니다 — 2편이 지금 그 길의 어디쯤인지, "
                "그리고 지금 배수가 그대로 유지되면 최종이 어디에 닿는지(연한 파란 점선)를 "
                "같이 그립니다.")

    a = m2d[["day", "cum", "adm", "screens"]].copy()
    a["구분"] = "2편"
    b = m1d[m1d["day"] <= vspan][["day", "cum", "adm", "screens"]].copy()
    b["구분"] = "1편"
    comp = pd.concat([a, b], ignore_index=True)

    wk_band = weekend_band(vspan, opacity=0.12 if not view_all else 0.09)

    _pt = vspan <= 40          # 141일을 점까지 찍으면 선이 안 보인다
    _xaxis = (alt.Axis(tickMinStep=1, format="d") if not view_all
              else alt.Axis(values=list(range(0, vspan + 1, 7)), format="d", labelAngle=0))
    base = alt.Chart(comp).encode(
        x=alt.X("day:Q", title="개봉 후 경과일 (0 = 개봉일)",
                scale=alt.Scale(domain=[0, vspan], nice=False), axis=_xaxis),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                 range=[C_M2, C_M1]),
                        legend=alt.Legend(title=None, orient="top-left")))
    cum_line = base.mark_line(point=_pt, strokeWidth=2.5).encode(
        y=alt.Y("cum:Q", title="누적 관객수", axis=alt.Axis(format=",.0f")),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                           range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                 alt.Tooltip("cum:Q", title="누적", format=","),
                 alt.Tooltip("adm:Q", title="당일", format=","),
                 alt.Tooltip("screens:Q", title="스크린", format=",")])

    _m2p = int((bonow or {}).get("m2_preview", 0))
    _m1p = int((bonow or {}).get("m1_preview", 0))
    cum_layers = [wk_band, cum_line]

    # 전체보기에서만: 지금 배수를 그대로 끌고 갔을 때 2편이 그리게 될 경로.
    # 1편 곡선을 배수로 늘린 것 = 배수의 정의 그대로라, 새 계수를 지어내지 않는다.
    proj = None
    if view_all and len(ref):
        _ratio = (int(last_bo["cum"]) - _m2p) / max(1, int(ref.iloc[0]["cum"]) - _m1p)
        proj = m1d[m1d["day"] >= dnum][["day", "cum"]].copy()
        proj["cum"] = _m2p + (proj["cum"] - _m1p) * _ratio
        proj["구분"] = "2편 예상 경로"
        cum_layers.append(
            alt.Chart(proj).mark_line(strokeWidth=2, strokeDash=[2, 3],
                                      color="#8fc0f0", opacity=0.95).encode(
                x=alt.X("day:Q", scale=alt.Scale(domain=[0, vspan], nice=False)),
                y="cum:Q",
                tooltip=[alt.Tooltip("구분:N", title=""),
                         alt.Tooltip("day:Q", title="경과일"),
                         alt.Tooltip("cum:Q", title="예상 누적", format=",.0f")]))
        _proj_end = float(proj["cum"].iloc[-1])
        goals = pd.DataFrame([
            {"y": m1_final, "t": f"1편 최종 {m1_final / 10000:.0f}만"},
            {"y": 2000000, "t": "200만 (예매가 약속했던 선)"},
            {"y": _proj_end, "t": f"지금 배수 유지 시 {_proj_end / 10000:.0f}만"},
        ])
        cum_layers.append(alt.Chart(goals).mark_rule(
            color="#9c9891", strokeDash=[6, 4], strokeWidth=1).encode(y="y:Q"))
        cum_layers.append(alt.Chart(goals).mark_text(
            align="left", dx=6, dy=-6, fontSize=11, color="#6f6b66").encode(
            x=alt.value(4), y="y:Q", text="t:N"))

    st.altair_chart(alt.layer(*cum_layers).properties(height=340), width="stretch")
    st.caption(f"⚫ 파란 실선 = 2편 · 주황 점선 = 1편 (최종 {m1_final:,}명) · 같은 경과일끼리 비교 · "
               "🟡 노란 음영 = **주말(토·일)** — 두 편 다 수요일에 개봉해서 경과일이 요일까지 똑같이 "
               "겹칩니다 (D+3·4가 첫 주말). 음영 구간에서 파란 선이 주황 선보다 가파르면 주말 수요가 "
               "1편보다 강하다는 뜻입니다 · "
               + (f"연한 파란 점선 = **2편 예상 경로** (지금 배수를 끝까지 유지했을 때) — 끝점 "
                  f"**{_proj_end / 10000:.0f}만**은 맨 위 '최종 예상 {ratio * m1_final / 10000:.0f}만'보다 "
                  f"조금 낮은데, 맨 위는 1편 최종에 배수를 곱한 값이라 1편의 큰 유료시사"
                  f"({_m1p:,}명)까지 같이 불어나기 때문입니다. 이 점선은 2편 실제 시사"
                  f"({_m2p:,}명)를 그대로 두고 그린 것이라 조금 더 보수적입니다 · "
                  if (view_all and proj is not None) else "")
               + f"그래프의 누적에는 유료시사(1편 {_m1p:,}명 / 2편 {_m2p:,}명)가 포함돼 있어 "
                 "출발선이 다릅니다 — 위의 배수는 그 시사분을 뺀 값입니다")

    # ---- 일별 유입 관객수 — 누적은 과거를 다 안고 가서 둔하다. 하루치는 오늘의 힘을
    # 그대로 보여주고, 주말 봉우리가 얼마나 높고 평일 골이 얼마나 얕은지로 뒷심이 읽힌다.
    st.markdown("#### 하루 관객수 (일별 유입)")
    day_line = base.mark_line(point=_pt, strokeWidth=2.5).encode(
        y=alt.Y("adm:Q", title="하루 관객수", axis=alt.Axis(format=",.0f")),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                           range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                 alt.Tooltip("adm:Q", title="하루 관객", format=","),
                 alt.Tooltip("cum:Q", title="누적", format=","),
                 alt.Tooltip("screens:Q", title="스크린", format=",")])
    st.altair_chart(alt.layer(wk_band, day_line).properties(height=300), width="stretch")

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
          "내려앉는 톱니 모양이었습니다. 2편의 봉우리가 그보다 높고 골이 얕으면 최종은 더 커집니다. "
          "🟡 음영 = 주말 · 1편의 D+8 봉우리는 주말이 아니라 **광복절**(2024-08-15 목요일 공휴일)입니다 — "
          "2편은 광복절(2026-08-15)이 D+10 토요일과 겹쳐서 그 주말이 특히 중요합니다.")

    # ---- 상영기간 — 1편 실측으로 '얼마나 오래 가나'를 보여주고 2편의 현재 위치를 찍는다
    st.markdown("#### 상영기간 — 얼마나 오래 상영되나")
    fin1 = int(m1d["cum"].max())
    d90 = int(m1d.loc[m1d["cum"] >= 0.9 * fin1, "day"].min())      # 관객 90%가 모인 날
    d_run = int(m1d.loc[pd.to_numeric(m1d["shows"], errors="coerce") >= 100, "day"].max())
    d_end = int(m1d.loc[m1d["adm"] >= 1000, "day"].max())          # 하루 1,000명 밑 = 사실상 종영
    d_last = int(m1d["day"].max())

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("1편: 관객 90% 모인 날", f"D+{d90}", f"약 {round((d90 + 1) / 7)}주", delta_color="off")
    p2.metric("1편: 정상 상영 유지", f"D+{d_run}", "하루 100회 이상", delta_color="off")
    p3.metric("1편: 사실상 종영", f"D+{d_end}", "하루 1,000명 밑으로", delta_color="off")
    p4.metric("2편: 지금", f"D+{dnum}", f"1편 90% 시점까지 {max(0, d90 - dnum)}일 남음",
              delta_color="off")

    seg = pd.DataFrame([
        {"x0": 0,     "x1": d90,    "구간": f"① 관객 90%가 드는 구간 (~D+{d90})"},
        {"x0": d90,   "x1": d_run,  "구간": f"② 정상 상영 유지 (~D+{d_run})"},
        {"x0": d_run, "x1": d_end,  "구간": f"③ 상영 축소 (~D+{d_end})"},
        {"x0": d_end, "x1": d_last, "구간": f"④ 이벤트성 상영 (~D+{d_last})"},
    ])
    seg_bar = alt.Chart(seg).mark_bar(height=30).encode(
        x=alt.X("x0:Q", title="개봉 후 경과일", scale=alt.Scale(domain=[0, d_last], nice=False),
                axis=alt.Axis(values=[0, d90, d_run, d_end, d_last], format="d")),
        x2="x1:Q",
        color=alt.Color("구간:N", scale=alt.Scale(range=["#eb6834", "#f0915f", "#f5bd93", "#9c9891"]),
                        legend=alt.Legend(title=None, orient="bottom", columns=2)),
        tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("x0:Q", title="시작일"),
                 alt.Tooltip("x1:Q", title="끝일")])
    now_rule = alt.Chart(pd.DataFrame({"x": [dnum]})).mark_rule(
        color=C_M2, strokeWidth=3).encode(x="x:Q")
    now_text = alt.Chart(pd.DataFrame({"x": [dnum], "t": [f"◀ 2편 지금 (D+{dnum})"]})).mark_text(
        align="left", dx=6, dy=-24, fontSize=13, fontWeight="bold", color=C_M2).encode(
        x="x:Q", text="t:N")
    st.altair_chart(alt.layer(seg_bar, now_rule, now_text).properties(height=110),
                    width="stretch")
    st.caption(
        f"막대 = **1편의 실제 상영기간 {d_last + 1}일** (2024-08-07 → 12월 말)을 구간으로 나눈 것 · "
        f"파란 선 = 2편의 현재 위치. 한국 상업영화는 보통 **첫 3~4주 안에 최종 관객의 대부분**이 들고 "
        "실질 상영은 한 달 반~두 달 정도면 끝납니다. 가족 애니메이션은 방학·연휴를 따라 꼬리가 더 깁니다 — "
        f"1편도 관객의 90%는 D+{d90}({round((d90 + 1) / 7)}주)까지 들었지만, 그 뒤로도 주말 위주로 "
        f"D+{d_end}까지 버텼고 마지막 두 달은 하루 수십 명 수준의 이벤트 상영이었습니다. "
        "즉 승부는 사실상 **첫 7주** 안에 납니다.")

    # ---- 며칠 지나야 최종을 믿을 수 있나 — "지금 예상치가 얼마나 흔들릴 수 있나"
    # 원리: 예상 = 배수 × 1편 최종. 이미 든 관객은 확정이라 안 흔들리고, 흔들릴 수 있는
    # 건 '앞으로 들어올 몫'뿐이다. 1편 곡선에서 그날까지 최종의 몇 %가 들었는지(p)를
    # 읽으면, 남은 (1-p)만 오차가 된다. 꼬리가 1편과 ±TAIL 만큼 다를 수 있다고 보면
    # 예상치의 흔들림은 (1-p) × TAIL 로 줄어든다. 지어낸 계수는 TAIL 하나뿐이고,
    # 그 값은 화면에 그대로 적어 둔다.
    st.markdown("#### 며칠 지나야 최종을 믿을 수 있나")
    TAIL = 0.30
    m1_adj_final = m1_final - _m1p
    lock = m1d[["day", "cum"]].copy()
    lock["p"] = (lock["cum"] - _m1p) / m1_adj_final
    lock["err"] = (1 - lock["p"]).clip(lower=0) * TAIL

    def _first_day(limit):
        hit = lock.loc[lock["err"] <= limit, "day"]
        return int(hit.min()) if len(hit) else None

    d15, d10, d05 = _first_day(0.15), _first_day(0.10), _first_day(0.05)
    now_err = float(lock.loc[lock["day"] == dnum, "err"].iloc[0]) if (lock["day"] == dnum).any() else None
    now_p = float(lock.loc[lock["day"] == dnum, "p"].iloc[0]) if (lock["day"] == dnum).any() else None
    fc = (ratio * m1_final) if len(ref) else None

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("지금 예상치가 흔들릴 폭", f"±{now_err:.0%}" if now_err is not None else "—",
              (f"{fc * (1 - now_err) / 10000:,.0f}만 ~ {fc * (1 + now_err) / 10000:,.0f}만"
               if fc and now_err is not None else ""), delta_color="off")
    for col, lim, dd in ((q2, 0.15, d15), (q3, 0.10, d10), (q4, 0.05, d05)):
        if dd is None:
            col.metric(f"±{lim:.0%} 안으로", "—", delta_color="off")
        else:
            left = dd - dnum
            col.metric(f"±{lim:.0%} 안으로", f"D+{dd}",
                       "이미 지남" if left <= 0 else f"{left}일 뒤 ({round(left / 7, 1)}주)",
                       delta_color="off")

    # 밴드 차트 — 가운데 = 지금 예상치, 위아래 = 그날 기준 흔들릴 수 있는 폭.
    # 날이 갈수록 밴드가 좁아지는 그림이 곧 "언제 판정이 끝나나"에 대한 답이다.
    if fc:
        bandsp = min(m1_last_day, 70)
        bd_ = lock[lock["day"] <= bandsp].copy()
        bd_["lo"], bd_["hi"] = fc * (1 - bd_["err"]), fc * (1 + bd_["err"])
        band = alt.Chart(bd_).mark_area(color=C_M2, opacity=0.16).encode(
            x=alt.X("day:Q", title="개봉 후 경과일",
                    scale=alt.Scale(domain=[0, bandsp], nice=False),
                    axis=alt.Axis(values=list(range(0, bandsp + 1, 7)), format="d", labelAngle=0)),
            y=alt.Y("lo:Q", title="최종 관객수 예상 범위", axis=alt.Axis(format=",.0f")),
            y2="hi:Q",
            tooltip=[alt.Tooltip("day:Q", title="경과일"),
                     alt.Tooltip("p:Q", title="그날까지 드는 몫(1편)", format=".0%"),
                     alt.Tooltip("lo:Q", title="아래", format=",.0f"),
                     alt.Tooltip("hi:Q", title="위", format=",.0f")])
        mid = alt.Chart(pd.DataFrame({"y": [fc]})).mark_rule(
            color=C_M2, strokeWidth=2).encode(y="y:Q")
        lines = pd.DataFrame([{"y": m1_final, "t": f"1편 최종 {m1_final / 10000:.0f}만 (기본 성공선)"},
                              {"y": 2000000, "t": "200만 (예매가 약속했던 선)"}])
        gl = alt.Chart(lines).mark_rule(color="#9c9891", strokeDash=[6, 4]).encode(y="y:Q")
        gt = alt.Chart(lines).mark_text(align="left", dx=6, dy=-6, fontSize=11,
                                        color="#6f6b66").encode(
            x=alt.value(4), y="y:Q", text="t:N")
        nowr = alt.Chart(pd.DataFrame({"x": [dnum]})).mark_rule(
            color=C_M2, strokeWidth=3, opacity=0.7).encode(x="x:Q")
        nowt = alt.Chart(pd.DataFrame({"x": [dnum], "t": [f"오늘 D+{dnum}"]})).mark_text(
            align="left", dx=6, dy=8, fontSize=12, fontWeight="bold", color=C_M2).encode(
            x="x:Q", y=alt.value(10), text="t:N")
        st.altair_chart(alt.layer(weekend_band(bandsp, opacity=0.09,
                                               x_title="개봉 후 경과일"),
                                  band, mid, gl, gt, nowr, nowt).properties(height=300),
                        width="stretch")

    st.caption(
        f"파란 밴드 = 그날 기준으로 **예상 최종이 흔들릴 수 있는 범위**, 가운데 선 = 지금 예상치 "
        + (f"{fc:,.0f}명. " if fc else ". ")
        + "원리는 간단합니다 — 이미 극장에 든 관객은 확정이라 안 흔들리고, 흔들리는 건 "
          "**앞으로 들어올 몫**뿐입니다. 1편 곡선을 보면 D+"
        # 굵게 닫는 ** 앞이 '%'(구두점)면 마크다운이 안 먹는다 — 조사까지 감싼다
        + (f"{dnum}에는 **최종의 {now_p:.0%}가** 이미 들어와 있어서 " if now_p is not None else "…에 ")
        + f"남은 {1 - (now_p or 0):.0%}만 오차가 됩니다. 그 남은 몫이 1편과 최대 ±{TAIL:.0%}까지 "
          f"다를 수 있다고 보면 지금 예상치의 폭은 ±{(now_err or 0):.0%}입니다. "
        + (f"**D+{d10}(오늘로부터 {max(0, d10 - dnum)}일 뒤)면 ±10% 안으로 좁혀져** "
           "그때는 200만을 넘을 수 있는지 없는지가 사실상 갈립니다. " if d10 else "")
        + (f"±5%까지 굳는 건 D+{d05}(약 {round((d05 + 1) / 7)}주차)입니다. " if d05 else "")
        + f"±{TAIL:.0%}는 저희가 정한 유일한 가정값이고, 나머지는 전부 1편 실측 곡선에서 나옵니다.")

    # ---- 배수 이력 — 자(1편)는 고정이니, 배수가 흔들리는지 굳는지가 곧 신뢰도다.
    hist = m2d[["day", "cum"]].merge(m1d[["day", "cum"]], on="day", suffixes=("_2", "_1"))
    if len(hist) > 1:
        hist["배수"] = (hist["cum_2"] - _m2p) / (hist["cum_1"] - _m1p).clip(lower=1)
        hist["예상"] = hist["배수"] * m1_final
        h1, h2 = st.columns([2, 1])
        with h1:
            rl = alt.Chart(hist).mark_line(point=True, strokeWidth=2.5, color=C_M2).encode(
                x=alt.X("day:Q", title="경과일", axis=alt.Axis(tickMinStep=1, format="d")),
                y=alt.Y("배수:Q", title="1편 대비 배수",
                        scale=alt.Scale(zero=False, nice=True), axis=alt.Axis(format=".2f")),
                tooltip=[alt.Tooltip("day:Q", title="경과일"),
                         alt.Tooltip("배수:Q", format=".3f"),
                         alt.Tooltip("예상:Q", title="그날 예상 최종", format=",.0f")])
            one = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
                color=C_M1, strokeDash=[5, 4]).encode(y="y:Q")
            _hspan = float(hist["day"].max())
            st.altair_chart(
                alt.layer(weekend_band(_hspan, x_title="경과일"), rl, one)
                .properties(height=230), width="stretch")
        with h2:
            _r0, _rn = float(hist["배수"].iloc[0]), float(hist["배수"].iloc[-1])
            _rp = float(hist["배수"].iloc[-2])
            st.metric("배수 (어제)", f"{_rn:.3f}배", f"{_rn - _rp:+.3f} (그 전날 대비)")
            st.metric("개봉일 배수에서", f"{_rn - _r0:+.3f}",
                      f"{_r0:.3f} → {_rn:.3f}", delta_color="off")
            st.caption("주황 점선 = 1.00배(1편과 동일). 배수가 **평평해지면** 그 숫자가 "
                       "최종이라고 믿어도 되는 때고, 계속 내려가면 위 밴드의 아래쪽으로 "
                       "붙는다는 뜻입니다.")

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
        line = alt.Chart(supply.dropna(subset=[ycol])).mark_line(point=True).encode(
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
        )
        return alt.layer(weekend_band(span, x_title="경과일"), line).properties(height=220)

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
    st.caption("🟡 음영 = 주말(토·일) — 다섯 개 차트 모두 같은 경과일 축이라 "
               "주말 봉우리와 평일 골이 어디인지 한눈에 맞춰 볼 수 있습니다.")
    st.caption("위 네 개는 극장이 이 영화에 **얼마나 걸어줬나(공급)**, 좌석점유율은 "
               "관객이 **얼마나 채웠나(수요)** 입니다. 공급은 극장이 정하고 수요는 관객이 정하므로, "
               "좌석점유율이 높으면 다음 주 스크린이 늘어나는 쪽으로 이어집니다 — 그래서 남겨 뒀습니다.")

    # ---- 경쟁작 상영점유율 — 상영관 총량은 고정이라, 대작이 빠져야 하츄핑 회차가 늘 수 있다.
    st.markdown("#### 경쟁작 상영점유율 — 상영관 뺏고 뺏기기")
    st.caption("극장 전체 상영 횟수는 정해져 있어서, 하츄핑 상영이 늘려면 **다른 영화가 줄어야** 합니다. "
               "오디세이·스파이더맨 같은 대작의 점유율이 내려가는 것이 하츄핑 상영 확대의 선행 신호입니다. "
               "1편 때 실제로 어땠는지도 같이 볼 수 있습니다.")

    def _mknum(df):
        df = df.copy()
        for c in ("day", "rank", "adm", "shows", "adm_share", "show_share"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["day", "show_share"])

    def market_lines(mk, mspan, top_n=6):
        df = _mknum(mk)
        df = df[df["day"] <= mspan]
        keep = df.groupby("title")["show_share"].max().nlargest(top_n).index
        df = df[df["title"].isin(keep)].copy()
        df["영화"] = df["title"].str.replace(r"[:\-].*$", "", regex=True).str.slice(0, 11).str.strip()
        # 축을 실측이 있는 날까지만 잡는다 — span 은 앞으로 들어올 날까지 미리 잡아 둔
        # 값이라(개봉 7일차인데 14일까지), 그대로 쓰면 선이 왼쪽 절반에 몰려 눌린다.
        _lo = float(df["day"].min())
        _hi = min(float(mspan), float(df["day"].max()) + 0.4)
        lines = alt.Chart(df).mark_line(point=True).encode(
            x=alt.X("day:Q", title="경과일 (0 = 하츄핑 개봉일)",
                    scale=alt.Scale(domain=[_lo, _hi], nice=False),
                    axis=alt.Axis(tickMinStep=1, format="d")),
            y=alt.Y("show_share:Q", title="상영점유율", axis=alt.Axis(format=".0%")),
            color=alt.Color("영화:N", legend=alt.Legend(title=None, orient="bottom", columns=6)),
            strokeWidth=alt.condition("indexof(datum.영화, '하츄핑') >= 0",
                                      alt.value(3.5), alt.value(1.4)),
            opacity=alt.condition("indexof(datum.영화, '하츄핑') >= 0",
                                  alt.value(1), alt.value(0.65)),
            tooltip=[alt.Tooltip("영화:N"), alt.Tooltip("date:T", title="날짜", format="%m/%d"),
                     alt.Tooltip("rank:Q", title="순위"),
                     alt.Tooltip("show_share:Q", title="상영점유율", format=".1%"),
                     alt.Tooltip("adm_share:Q", title="관객점유율", format=".1%"),
                     alt.Tooltip("adm:Q", title="하루 관객", format=",")],
        )
        band = weekend_band(_hi, lo=_lo, x_title="경과일 (0 = 하츄핑 개봉일)")
        return alt.layer(band, lines).properties(height=340)

    def share_vs_adm(daily, bar_color, mspan):
        df = daily[daily["day"] <= mspan][["day", "adm", "show_share"]].copy()
        df["show_share"] = pd.to_numeric(df["show_share"], errors="coerce")
        # 위 경쟁작 차트와 같은 이유로 빈 날짜까지 축을 늘리지 않는다 (막대도 그만큼 굵어진다)
        _hi = min(float(mspan), float(df["day"].max()) + 0.6)
        x = alt.X("day:Q", title="경과일", scale=alt.Scale(domain=[-0.6, _hi], nice=False),
                  axis=alt.Axis(tickMinStep=1, format="d"))
        bars = alt.Chart(df).mark_bar(color=bar_color, opacity=0.45).encode(
            x=x, y=alt.Y("adm:Q", title="하루 관객수", axis=alt.Axis(format=",.0f")),
            tooltip=[alt.Tooltip("day:Q", title="경과일"),
                     alt.Tooltip("adm:Q", title="하루 관객", format=","),
                     alt.Tooltip("show_share:Q", title="상영점유율", format=".1%")])
        line = alt.Chart(df.dropna(subset=["show_share"])).mark_line(
            color="#7c3aed", strokeWidth=2.5, point=True).encode(
            x=x, y=alt.Y("show_share:Q", title="상영점유율", axis=alt.Axis(format=".0%")),
            tooltip=[alt.Tooltip("day:Q", title="경과일"),
                     alt.Tooltip("show_share:Q", title="상영점유율", format=".1%")])
        band = weekend_band(_hi, lo=-0.6, x_title="경과일")
        return (alt.layer(band, bars, line).resolve_scale(y="independent")
                .properties(height=300))

    tab2, tab1 = st.tabs(["2편 지금 (2026)", "1편 그때는 (2024)"])
    with tab2:
        if mk2 is None or not len(mk2):
            st.info("경쟁작 데이터 수집 전입니다 — 매일 아침 자동으로 쌓입니다.")
        else:
            st.altair_chart(market_lines(mk2, span), width="stretch")
            mlast = _mknum(mk2)
            mlast = mlast[mlast["day"] == mlast["day"].max()].sort_values("rank")
            hat = mlast[mlast["title"].str.contains("하츄핑")]
            if len(hat):
                h = hat.iloc[0]
                gap = h["adm_share"] - h["show_share"]
                st.caption(f"어제 하츄핑: 상영점유율 **{h['show_share']:.1%}** vs 관객점유율 "
                           f"**{h['adm_share']:.1%}** ({gap:+.1%}p) — "
                           + ("관객점유율이 더 높으면 '자리가 모자라다'는 뜻이라 "
                              "극장이 상영을 늘릴 유인이 있습니다."
                              if gap > 0 else
                              "관객점유율이 상영점유율보다 낮으면 극장이 상영을 줄일 수 있습니다.")
                           + " 위 경쟁작 선이 꺾이는 날 = 하츄핑 회차가 늘 수 있는 날입니다.")
            st.markdown("**하츄핑2 — 상영점유율(보라 선)과 하루 관객수(막대)**")
            st.altair_chart(share_vs_adm(m2d, C_M2, span), width="stretch")
    with tab1:
        if mk1 is None or not len(mk1):
            st.info("1편 경쟁작 데이터가 없습니다 — `python boxoffice_update.py --build-m1-market` 실행 필요")
        else:
            m1span = 45
            st.altair_chart(market_lines(mk1, m1span), width="stretch")
            st.markdown("**하츄핑1 — 상영점유율(보라 선)과 하루 관객수(막대): 점유율이 움직이면 관객이 어떻게 따라갔나**")
            st.altair_chart(share_vs_adm(m1d, C_M1, m1span), width="stretch")
            st.caption("1편의 교훈: 상영점유율은 주말마다 올라가고 평일에 내려가는 톱니 모양이었고, "
                       "8월 중순 대작들이 빠지면서 점유율이 유지된 구간에서 관객이 계속 들어왔습니다. "
                       "점유율(공급)이 먼저 움직이고 관객수(수요)가 따라오는지 — 그 순서를 보는 차트입니다.")

    # ---- 1편 vs 2편 상영점유율 오버레이 — 극장이 걸어주는 비중 = 인기도의 대리 지표.
    # 위 탭은 '그 해 경쟁작들 속에서'를 보여주고, 이 차트는 두 편끼리 직접 겹쳐 본다.
    st.markdown("#### 하츄핑 1편 vs 2편 — 상영점유율 비교 (인기도 추적)")
    st.caption("상영점유율 = 그날 전국 전체 상영 횟수 중 하츄핑이 차지한 비중. "
               "극장은 인기를 보고 다음 주 회차를 정하니, 이 선이 1편 곡선 위에 있으면 "
               "극장들이 2편을 1편 때보다 더 좋게 보고 있다는 뜻입니다.")
    cmp_span = 45
    share_cmp = pd.concat([
        m2d.assign(구분="2편"),
        m1d[m1d["day"] <= cmp_span].assign(구분="1편"),
    ], ignore_index=True)[["day", "구분", "show_share", "adm"]]
    share_cmp["show_share"] = pd.to_numeric(share_cmp["show_share"], errors="coerce")
    share_cmp = share_cmp.dropna(subset=["show_share"])

    cmp_chart = alt.Chart(share_cmp).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("day:Q", title="개봉 후 경과일 (0 = 개봉일)",
                scale=alt.Scale(domain=[0, cmp_span], nice=False),
                axis=alt.Axis(tickMinStep=1, format="d")),
        y=alt.Y("show_share:Q", title="상영점유율", axis=alt.Axis(format=".0%")),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                 range=[C_M2, C_M1]),
                        legend=alt.Legend(title=None, orient="top-right")),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                           range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                 alt.Tooltip("show_share:Q", title="상영점유율", format=".1%"),
                 alt.Tooltip("adm:Q", title="하루 관객", format=",")])
    st.altair_chart(
        alt.layer(weekend_band(cmp_span, x_title="개봉 후 경과일 (0 = 개봉일)"), cmp_chart)
        .properties(height=300), width="stretch")

    _s2 = share_cmp[share_cmp["구분"] == "2편"]
    if len(_s2):
        _d = int(_s2["day"].max())
        _v2 = float(_s2[_s2["day"] == _d]["show_share"].iloc[0])
        _r1 = share_cmp[(share_cmp["구분"] == "1편") & (share_cmp["day"] == _d)]
        if len(_r1):
            _v1 = float(_r1["show_share"].iloc[0])
            st.caption(f"어제(경과 {_d}일) 상영점유율: 2편 **{_v2:.1%}** vs 1편 같은 일차 **{_v1:.1%}** "
                       f"(**{_v2 - _v1:+.1%}p**) — "
                       + ("2편이 1편 때보다 극장을 더 많이 잡고 있습니다."
                          if _v2 >= _v1 else
                          "아직 1편 때만큼 극장을 잡지 못하고 있습니다.")
                       + " 1편은 45일차까지 표시 — 주말마다 오르고 평일에 내리는 톱니 모양이 정상입니다.")

    # ---- 체인별 상영현황 — 같은 '상영을 얼마나 걸어주나'를 체인(극장 회사) 단위로 쪼개 본다.
    # KOBIS 체인영화관별 통계는 하루 상위 5편만 제공 — 하츄핑이 5위 밖으로 밀리면 그날은 빈다.
    if chn is not None and len(chn):
        st.markdown("#### 체인별 상영현황 — CGV·롯데·메가박스가 얼마나 걸어주나")
        st.caption("상영 확대 결정은 체인 본사가 내립니다. 어느 체인이 하츄핑에 후하게 회차를 "
                   "주는지, 그리고 그 차이가 벌어지는지 좁혀지는지를 봅니다 — 한 체인의 선이 "
                   "혼자 올라가면 그 체인이 먼저 움직였다는 뜻이고 나머지가 따라오는 경우가 많습니다.")
        chd = chn.copy()
        chd["show_share"] = pd.to_numeric(chd["show_share"], errors="coerce")
        mine_ch = chd[chd["title"].str.contains("하츄핑", na=False)
                      & (chd["chain"] != "기타")].dropna(subset=["show_share"])
        CH_ORDER = ["전체", "CGV", "롯데시네마", "메가박스", "씨네Q"]
        CH_COLORS = [C_M2, "#e03131", "#f08c00", "#6741d9", "#2f9e44"]
        ch_chart = alt.Chart(mine_ch).mark_line(point=True, strokeWidth=2.5).encode(
            x=alt.X("date:T", title=None, axis=day_axis(mine_ch["date"].unique())),
            y=alt.Y("show_share:Q", title="하츄핑 상영점유율 (그 체인 안에서)",
                    axis=alt.Axis(format=".0%")),
            color=alt.Color("chain:N", scale=alt.Scale(domain=CH_ORDER, range=CH_COLORS),
                            legend=alt.Legend(title=None, orient="top-left")),
            strokeDash=alt.StrokeDash("chain:N", scale=alt.Scale(domain=CH_ORDER,
                                                                 range=[[1, 0]] + [[4, 3]] * 4),
                                      legend=None),
            tooltip=[alt.Tooltip("date:T", title="날짜", format="%m/%d"),
                     alt.Tooltip("chain:N", title="체인"),
                     alt.Tooltip("show_share:Q", title="상영점유율", format=".1%"),
                     alt.Tooltip("shows:Q", title="상영횟수", format=",")])
        st.altair_chart(
            alt.layer(weekend_band_dates(mine_ch["date"]), ch_chart).properties(height=300),
            width="stretch")

        # 체인 하나를 골라 들여다보기 — "CGV 는 지금 무엇에 회차를 몰아주나" / "1편 때와 비교하면?"
        st.markdown("**🎯 체인을 골라 들여다보기**")
        cc1, cc2 = st.columns([3, 2])
        sel_ch = cc1.radio("체인 선택", CH_ORDER, horizontal=True, index=1,
                           label_visibility="collapsed")
        mode_ch = cc2.radio("보기 모드", ["영화별 비중", "1편 vs 2편"], horizontal=True,
                            label_visibility="collapsed")

        if mode_ch == "1편 vs 2편":
            if chn1 is None or not len(chn1):
                st.info("1편 체인별 데이터(m1_chains.csv)가 없습니다 — "
                        "`python boxoffice_update.py --build-m1-chains` 실행 필요")
            else:
                c1d = chn1.copy()
                c1d["show_share"] = pd.to_numeric(c1d["show_share"], errors="coerce")
                mine1 = c1d[c1d["title"].str.contains("하츄핑", na=False)
                            & (c1d["chain"] == sel_ch)].dropna(subset=["show_share"])
                mine2 = chd[chd["title"].str.contains("하츄핑", na=False)
                            & (chd["chain"] == sel_ch)].dropna(subset=["show_share"])
                span_c = max(int(mine2["day"].max()) + 7, 21) if len(mine2) else 21
                vs = pd.concat([
                    mine2.assign(구분="2편"),
                    mine1[mine1["day"] <= span_c].assign(구분="1편"),
                ], ignore_index=True)
                band_c = weekend_band(span_c, x_title="개봉 후 경과일 (0 = 개봉일)")
                vs_line = alt.Chart(vs).mark_line(point=True, strokeWidth=2.5).encode(
                    x=alt.X("day:Q", title="개봉 후 경과일 (0 = 개봉일)",
                            scale=alt.Scale(domain=[0, span_c], nice=False),
                            axis=alt.Axis(tickMinStep=1, format="d")),
                    y=alt.Y("show_share:Q", title=f"{sel_ch} 안에서 하츄핑 상영점유율",
                            axis=alt.Axis(format=".0%")),
                    color=alt.Color("구분:N", scale=alt.Scale(domain=["2편", "1편"],
                                                             range=[C_M2, C_M1]),
                                    legend=alt.Legend(title=None, orient="top-right")),
                    strokeDash=alt.StrokeDash("구분:N",
                                              scale=alt.Scale(domain=["2편", "1편"],
                                                              range=[[1, 0], [5, 4]]),
                                              legend=None),
                    tooltip=[alt.Tooltip("구분:N"), alt.Tooltip("day:Q", title="경과일"),
                             alt.Tooltip("show_share:Q", title="상영점유율", format=".1%"),
                             alt.Tooltip("shows:Q", title="상영횟수", format=",")])
                st.altair_chart(alt.layer(band_c, vs_line).properties(height=380),
                                width="stretch")
                _v1r = mine1[mine1["day"] == int(mine2["day"].max())] if len(mine2) else []
                _gap = ""
                if len(mine2) and len(_v1r):
                    _a = float(mine2[mine2["day"] == mine2["day"].max()]["show_share"].iloc[0])
                    _b = float(_v1r["show_share"].iloc[0])
                    _gap = (f" 어제 같은 일차: 2편 **{_a:.1%}** vs 1편 **{_b:.1%}** "
                            f"({_a - _b:+.1%}p).")
                st.caption(f"{sel_ch} 전체 상영횟수 중 하츄핑 비중 — 파란 실선 = 2편, "
                           f"주황 점선 = 1편 같은 경과일, 🟡 음영 = 주말.{_gap} "
                           "1편은 하루 상위 5편에 든 날만 데이터가 있어 선이 끊길 수 "
                           "있습니다 (D+53까지 20일).")

        one_ch = chd[chd["chain"] == sel_ch].dropna(subset=["show_share"]).copy()
        if mode_ch == "영화별 비중" and len(one_ch):
            # 색: 하츄핑 = 파랑 고정, 나머지는 최신 순위 순서로 배정 (날마다 색이 안 바뀌게)
            latest = one_ch[one_ch["date"] == one_ch["date"].max()].sort_values("rank")
            others = [t for t in latest["title"] if "하츄핑" not in t]
            others += [t for t in one_ch["title"].unique()
                       if t not in others and "하츄핑" not in t]
            mine_title = next((t for t in one_ch["title"].unique() if "하츄핑" in t), None)
            dom = ([mine_title] if mine_title else []) + others
            pal = [C_M2] if mine_title else []
            pal += ["#e03131", "#f08c00", "#6741d9", "#2f9e44", "#868e96",
                    "#0ca678", "#d6336c", "#846358"][:len(others)]
            movie_chart = alt.Chart(one_ch).mark_line(point=True).encode(
                x=alt.X("date:T", title=None, axis=day_axis(one_ch["date"].unique())),
                y=alt.Y("show_share:Q", title=f"{sel_ch} 안에서 영화별 상영점유율",
                        axis=alt.Axis(format=".0%")),
                color=alt.Color("title:N", scale=alt.Scale(domain=dom, range=pal),
                                legend=alt.Legend(title=None, orient="right",
                                                  labelLimit=240)),
                strokeWidth=alt.condition("indexof(datum.title, '하츄핑') >= 0",
                                          alt.value(3.5), alt.value(1.6)),
                tooltip=[alt.Tooltip("date:T", title="날짜", format="%m/%d"),
                         alt.Tooltip("title:N", title="영화"),
                         alt.Tooltip("show_share:Q", title="상영점유율", format=".1%"),
                         alt.Tooltip("shows:Q", title="상영횟수", format=","),
                         alt.Tooltip("screens:Q", title="스크린수", format=",")])
            st.altair_chart(
                alt.layer(weekend_band_dates(one_ch["date"]), movie_chart)
                .properties(height=460), width="stretch")
            st.caption(f"{sel_ch} 전체 상영횟수 중 각 영화가 차지한 비중 (KOBIS 하루 상위 5편). "
                       "굵은 파란 선 = 하츄핑. 대작 선이 내려가면서 하츄핑 선이 올라가면 "
                       "그 체인이 회차를 하츄핑 쪽으로 돌리고 있다는 뜻입니다.")

        # 어제 스냅샷 — 상위 영화 × 체인 상영점유율 표
        last_ch = chd["date"].max()
        snap = chd[(chd["date"] == last_ch) & (chd["chain"] != "기타")]
        if len(snap):
            piv = snap.pivot_table(index=["rank", "title"], columns="chain",
                                   values="show_share", aggfunc="first").reset_index()
            piv = piv.sort_values("rank")
            cols = [c for c in CH_ORDER if c in piv.columns]
            md = ["| 순위 | 영화 | " + " | ".join(cols) + " |",
                  "|---:|---|" + "---:|" * len(cols)]
            for _, r in piv.iterrows():
                name = str(r["title"])
                cells = " | ".join(f"{r[c]:.1%}" if pd.notna(r[c]) else "—" for c in cols)
                line_ = f"| {int(r['rank'])} | {name[:16]} | {cells} |"
                if "하츄핑" in name:
                    line_ = f"| **{int(r['rank'])}** | **🐳 {name[:16]}** | " + " | ".join(
                        f"**{r[c]:.1%}**" if pd.notna(r[c]) else "—" for c in cols) + " |"
                md.append(line_)
            _lc = pd.Timestamp(last_ch)
            st.markdown(f"**어제({_lc.month}/{_lc.day}) 상위 영화 × 체인별 상영점유율** "
                        "— 각 칸 = 그 체인 전체 상영횟수 중 그 영화의 비중")
            st.markdown("\n".join(md))
            mine_row = piv[piv["title"].str.contains("하츄핑", na=False)]
            if len(mine_row) and {"롯데시네마", "CGV"} <= set(piv.columns):
                _lot = mine_row["롯데시네마"].iloc[0]
                _cgv = mine_row["CGV"].iloc[0]
                if pd.notna(_lot) and pd.notna(_cgv):
                    st.caption(f"현재 하츄핑에 가장 후한 체인 대비 CGV 차이: 롯데시네마 {_lot:.1%} vs "
                               f"CGV {_cgv:.1%} ({_lot - _cgv:+.1%}p). 어린이 관객 비중이 높은 "
                               "체인일수록 후하게 주는 경향이 있고, CGV가 롯데 수준으로 올라오는 것 "
                               "자체가 흥행 확산 신호입니다. (KOBIS 체인별 통계는 하루 상위 5편만 "
                               "제공 — 하츄핑이 5위 밖이면 그날 칸이 빕니다)")

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
        layers = [weekend_band_dates(eg["date"]), line]
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
            st.altair_chart(
                alt.layer(weekend_band_dates(sd["date"]), ch).properties(height=260),
                width="stretch")
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
        st.altair_chart(
            alt.layer(weekend_band_dates(bdd["date"]), bar).properties(height=240),
            width="stretch")
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
        st.altair_chart(
            alt.layer(weekend_band_dates(bdd["date"]), ln).properties(height=240),
            width="stretch")

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
    # D-day 축에도 같은 주말 규칙이 그대로 이어진다 — 두 편 다 수요일 개봉이라
    # D+3·4 뿐 아니라 개봉 전 D-4·D-3 도 토·일이다.
    dband = weekend_band(30, lo=-40, x_title="개봉일 기준 D-day")
    st.altair_chart(alt.layer(dband, lines, zero).properties(height=320), width="stretch")

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
    st.altair_chart(alt.layer(dband, bars, zero).properties(height=240), width="stretch")
    st.caption("참고: 티니핑 프랜차이즈 자체가 2024년보다 커져서, YoY의 일부는 영화가 아닌 "
               "브랜드 성장분일 수 있습니다. 그래도 모든 D-day에서 1편 곡선 위에 있으면 좋은 신호.")

    with st.expander("매일 기록 표 (언급량, 채널별)"):
        st.dataframe(bz.sort_values("date", ascending=False), hide_index=True, width="stretch")
    st.caption("데이터: 썸트렌드(some.co.kr) · 엑셀 원본: Heartuping movie 2_Buzz trend_v1.xlsx "
               "'D-day 비교' 시트와 동일한 계산")

