# -*- coding: utf-8 -*-
"""YG플러스 (037270) — 앨범 유통 물량 vs 매출 · 장당 단가.

원본 엑셀: Companies\\band chart\\기업분석 by 클로드_추후 반영\\YG플러스_Analysis template_2026 09_v03.xlsx
           ('앨범유통 단가' 시트). 데이터 갱신: python circle_dist_update.py → python ygplus_album_update.py
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "ygplus"
C_BAR, C_LINE, C_GOLD, C_GREEN, C_GREY = "#2a78d6", "#eb6834", "#e8c15a", "#3fb27f", "#8a97aa"

st.set_page_config(page_title="YG플러스 앨범유통", page_icon="💿", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("ent")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 6px 12px; margin: 0.9rem 0 0.5rem 0; }
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


def _stamp(name):
    p = DATA / name
    return round(p.stat().st_mtime, 3) if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def load(name, stamp):
    p = DATA / name
    return pd.read_csv(p) if p.exists() else None


def get(name):
    return load(name, _stamp(name))


REV = {"음악서비스매출": "음악서비스매출 (음원·음반 유통 + 네이버 플랫폼)",
       "용역매출": "용역매출 (매니지먼트·행사 대행)",
       "상ㆍ제품매출": "상ㆍ제품매출 (MD·굿즈)",
       "합계": "합계 매출"}

st.title("YG플러스 — 앨범 유통 물량 vs 매출")
meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8")) if (DATA / "meta.json").exists() else {}
st.caption("와이지플러스 (037270) · 물량 = 써클차트 월간 앨범차트 톱100 중 유통사 **YG PLUS** 행의 출하량−반품량 · "
           "매출 = DART 매출유형별 · 갱신 " + str(meta.get("as_of", "—")) +
           " · 원본 엑셀: Companies/band chart/기업분석 by 클로드_추후 반영/YG플러스_Analysis template …_v03 ('앨범유통 단가' 시트)")

q = get("quarterly.csv")
m = get("units_month.csv")
a = get("annual.csv")
top = get("top_albums.csv")
if q is None:
    st.error("데이터가 없습니다 — python circle_dist_update.py → python ygplus_album_update.py 를 실행하세요.")
    st.stop()

qf = q[(q["n_month"] == 3) & (q["q"] >= "2021Q3")].copy()
d = qf.dropna(subset=["units", "음악서비스매출"])
slope, icept = np.polyfit(d["units"], d["음악서비스매출"], 1)
r = float(np.corrcoef(d["units"], d["음악서비스매출"])[0, 1])
last = qf.iloc[-1]

st.info(f"**한 줄 결론** — 음악서비스매출은 **고정 기반 + 앨범 연동분**입니다. "
        f"분기당 약 **{icept:,.0f}백만원**은 앨범과 상관없이 들어오는 기반(네이버 음악플랫폼 운영대행 + 음원 스트리밍)이고, "
        f"앨범이 **100만 장 더 돌 때 약 {slope * 1e6:,.0f}백만원**이 붙습니다(= 약 **{slope * 1e6:,.0f}원/장**, R = {r:+.2f}). "
        f"그래서 '분기 매출 ÷ 물량'으로 구한 평균 단가는 앨범이 적은 분기에 커 보이는 착시가 있습니다 — 수준이 아니라 기울기를 보세요.")

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{last['q']} 유통 물량", f"{last['units'] / 1e4:,.0f}만장", f"점유율 {last['share']:.0%}", delta_color="off")
c2.metric(f"{last['q']} 음악서비스매출", f"{last['음악서비스매출'] / 1000:,.1f}십억원",
          f"평균 단가 {last['음악서비스매출'] * 1e6 / last['units']:,.0f}원/장", delta_color="off")
c3.metric("앨범 100만장당 (회귀)", f"{slope * 1e6:,.0f}백만원", f"R = {r:+.2f}", delta_color="off")
c4.metric("앨범과 무관한 기반", f"{icept:,.0f}백만원/분기", "네이버 플랫폼 + 음원", delta_color="off")

tab1, tab2, tab3 = st.tabs(["📊 물량 vs 매출", "📈 장당 단가", "💿 유통 앨범"])

with tab1:
    sub("분기 — 유통 물량(막대)과 매출(선)", "물량 = 만장 · 매출 = 십억원 · 2021Q3부터 DART 매출유형 공시")
    base = alt.Chart(qf).encode(x=alt.X("q:O", title=None, axis=alt.Axis(labelAngle=-45)))
    bars = base.mark_bar(color=C_BAR, opacity=0.85).encode(
        y=alt.Y("만장:Q", title="유통 물량 (만장)"),
        tooltip=["q", alt.Tooltip("만장", format=",.0f"), alt.Tooltip("share", title="점유율", format=".1%")])
    qf["만장"] = qf["units"] / 1e4
    pick = st.multiselect("같이 볼 매출", list(REV), default=["음악서비스매출", "상ㆍ제품매출"], key="yp_rev")
    long = qf.melt(id_vars=["q"], value_vars=[c for c in pick if c in qf.columns],
                   var_name="매출유형", value_name="십억원")
    long["십억원"] = long["십억원"] / 1000
    bars = alt.Chart(qf).mark_bar(color=C_BAR, opacity=0.8).encode(
        x=alt.X("q:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("만장:Q", title="유통 물량 (만장)"),
        tooltip=["q", alt.Tooltip("만장", format=",.0f"), alt.Tooltip("share", title="점유율", format=".1%")])
    line = alt.Chart(long).mark_line(point=True, size=2.5).encode(
        x=alt.X("q:O", title=None), y=alt.Y("십억원:Q", title="매출 (십억원)"),
        color=alt.Color("매출유형:N", title=None, scale=alt.Scale(range=[C_LINE, C_GREEN, C_GOLD, C_GREY]),
                        legend=alt.Legend(orient="top")),
        tooltip=["q", "매출유형", alt.Tooltip("십억원", format=",.1f")])
    st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=420),
                    use_container_width=True)
    st.caption("**읽는법**: 파란 막대(앨범 물량)가 커질 때 주황선(음악서비스매출)이 조금만 따라 오릅니다 — "
               "고정 기반이 크기 때문입니다. 초록선(MD)은 물량을 더 잘 따라갑니다(컴백하면 굿즈도 같이 팔림).")

    sub("관계 — 분기 물량 vs 매출", "점 = 분기 · 선 = 회귀")
    cc = st.columns(2)
    for i, name in enumerate(("음악서비스매출", "상ㆍ제품매출")):
        with cc[i]:
            dd = qf.dropna(subset=["units", name]).copy()
            dd["만장"] = dd["units"] / 1e4
            sc = alt.Chart(dd).mark_circle(size=110, color=C_BAR).encode(
                x=alt.X("만장:Q", title="유통 물량 (만장)"), y=alt.Y(f"{name}:Q", title=f"{name} (백만원)", scale=alt.Scale(zero=False)),
                tooltip=["q", alt.Tooltip("만장", format=",.0f"), alt.Tooltip(name, format=",.0f")])
            rr = float(np.corrcoef(dd["units"], dd[name])[0, 1])
            st.altair_chart((sc + sc.transform_regression("만장", name).mark_line(color=C_LINE, strokeDash=[5, 4]))
                            .properties(height=300, title=f"{name} · R = {rr:+.2f}"), use_container_width=True)

    sub("점유율 — 써클 톱100 안에서 YG PLUS 비중", "DART 공시 1H23 음반유통 점유율 41.5%와 같은 값(검증 완료)")
    mm = m.copy()
    mm["연"] = mm["month"].str[:4]
    ch = alt.Chart(mm[mm["month"] >= "2018-01"]).mark_area(opacity=0.5, color=C_GOLD, line={"color": C_GOLD}).encode(
        x=alt.X("month:T", title=None), y=alt.Y("share:Q", title="점유율", axis=alt.Axis(format="%")),
        tooltip=[alt.Tooltip("month", title="월"), alt.Tooltip("share", format=".1%"),
                 alt.Tooltip("ygplus_units", title="물량(장)", format=",.0f")])
    st.altair_chart(ch.properties(height=300), use_container_width=True)

with tab2:
    sub("장당 단가 — 분기 매출 ÷ 그 분기 유통 물량", "원/장 · 착시 주의(고정 기반이 나눠짐)")
    qq = qf.copy()
    for k in REV:
        if k in qq.columns:
            qq[k + "_원장"] = qq[k] * 1e6 / qq["units"]
    pick2 = st.multiselect("보고 싶은 매출", list(REV), default=["음악서비스매출", "합계"], key="yp_unit")
    lg = qq.melt(id_vars=["q"], value_vars=[k + "_원장" for k in pick2 if k + "_원장" in qq.columns],
                 var_name="구분", value_name="원장")
    lg["구분"] = lg["구분"].str.replace("_원장", "", regex=False)
    ch = alt.Chart(lg).mark_line(point=True, size=2.5).encode(
        x=alt.X("q:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("원장:Q", title="원 / 장"),
        color=alt.Color("구분:N", title=None, scale=alt.Scale(range=[C_LINE, C_GREEN, C_GOLD, C_GREY]),
                        legend=alt.Legend(orient="top")),
        tooltip=["q", "구분", alt.Tooltip("원장", format=",.0f")])
    st.altair_chart(ch.properties(height=380), use_container_width=True)
    st.caption("2021Q3 3,979원 → 2026Q2 1,938원처럼 내려가 보이지만, 이는 앨범 물량이 늘어 고정 기반이 더 많이 나눠진 결과입니다. "
               "'앨범 한 장이 실제로 만드는 매출'은 아래 회귀 기울기를 보세요.")

    sub("연간", "완전 연도만 · 매출은 백만원")
    ann = a[(a["n_month"] == 12) & (a["year"] >= 2018)].copy()
    show = ann[["year", "units", "share"] + [c for c in REV if c in ann.columns] +
               [c for c in ann.columns if c.endswith("_원장")]]
    show = show.rename(columns={"year": "연도", "units": "유통 물량(장)", "share": "점유율"})
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={"유통 물량(장)": st.column_config.NumberColumn(format="%,.0f"),
                                "점유율": st.column_config.NumberColumn(format="%.1f%%")})

    sub("회귀 요약", "2021Q3~ 완전분기, 물량 → 매출")
    rows = []
    for k in REV:
        if k not in qf.columns:
            continue
        dd = qf.dropna(subset=["units", k])
        if len(dd) < 4:
            continue
        b, i0 = np.polyfit(dd["units"], dd[k], 1)
        rows.append({"매출유형": REV[k], "상관 R": float(np.corrcoef(dd["units"], dd[k])[0, 1]),
                     "앨범 1장당 (원)": b * 1e6, "고정 기반 (백만원/분기)": i0,
                     "평균 단가 (원/장)": dd[k].sum() * 1e6 / dd["units"].sum()})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"상관 R": st.column_config.NumberColumn(format="%.2f"),
                                "앨범 1장당 (원)": st.column_config.NumberColumn(format="%,.0f"),
                                "고정 기반 (백만원/분기)": st.column_config.NumberColumn(format="%,.0f"),
                                "평균 단가 (원/장)": st.column_config.NumberColumn(format="%,.0f")})

with tab3:
    am = get("albums_month.csv")
    aw = get("albums_week.csv")
    uw = get("units_week.csv")

    UNITS = ["누적 (전체 기간)", "연간", "반기", "분기", "월간", "주간"]
    opts = [u for u in UNITS if u != "주간" or (aw is not None and len(aw))]
    unit = st.radio("기간 단위", opts, index=0, horizontal=True, key="yp_gran",
                    help="누적 = 2011년부터 전부 합친 순위. 나머지는 그 기간 안에서만 집계합니다. "
                         "주간은 써클 주간차트(일~토) 기준이라 매주 목요일 발표 후 갱신됩니다.")

    def periods(df, kind):
        """월별 표 → 선택한 단위의 기간 라벨 컬럼을 붙인다."""
        d = df.copy()
        y = d["month"].str[:4]
        mm = d["month"].str[5:7].astype(int)
        if kind == "연간":
            d["기간"] = y
        elif kind == "반기":
            d["기간"] = y + " " + np.where(mm <= 6, "상반기", "하반기")
        elif kind == "분기":
            d["기간"] = y + "Q" + ((mm - 1) // 3 + 1).astype(str)
        else:
            d["기간"] = d["month"]
        return d

    if unit == "주간":
        src = aw.rename(columns={"start": "기간"}).copy()
        src["라벨"] = src["기간"] + " ~ " + src["end"] + "  (" + src["year"].astype(str) + "-W" + src["week"].astype(str).str.zfill(2) + ")"
        lab = dict(zip(src["기간"], src["라벨"]))
        ts = uw.rename(columns={"start": "기간", "ygplus_units": "units", "market_units": "market"}).copy()
    elif unit == "누적 (전체 기간)":
        src = am.copy()
        src["기간"] = "전체"
        lab = {"전체": f"전체 누적 ({am['month'].min()} ~ {am['month'].max()})"}
        ts = None
    else:
        src = periods(am, unit)
        lab = {k: k for k in src["기간"].unique()}
        mu = m.rename(columns={"ygplus_units": "units", "market_units": "market"})
        ts = periods(mu, unit).groupby("기간", as_index=False).agg(units=("units", "sum"), market=("market", "sum"))
        ts["share"] = ts["units"] / ts["market"]

    # ---- 기간별 물량 추이 (누적 모드에서는 생략)
    if ts is not None and len(ts):
        sub(f"{unit} 유통 물량 추이", "YG PLUS 가 유통한 앨범 출하량 · 막대 = 물량, 선 = 써클 톱100 안 점유율")
        tt = ts.copy()
        tt["만장"] = tt["units"] / 1e4
        nlast = st.slider("최근 몇 개 기간", 6, min(len(tt), 200), min(len(tt), 24 if unit != "주간" else 60),
                          key="yp_nlast")
        tt = tt.sort_values("기간").tail(nlast)
        xenc = alt.X("기간:O", title=None, axis=alt.Axis(labelAngle=-45,
                                                        labelOverlap="greedy" if unit == "주간" else False))
        bars = alt.Chart(tt).mark_bar(color=C_BAR, opacity=0.85).encode(
            x=xenc, y=alt.Y("만장:Q", title="유통 물량 (만장)"),
            tooltip=["기간", alt.Tooltip("만장", format=",.1f"), alt.Tooltip("share", title="점유율", format=".1%")])
        line = alt.Chart(tt).mark_line(color=C_GOLD, size=2, point=True).encode(
            x=xenc, y=alt.Y("share:Q", title="점유율", axis=alt.Axis(format="%")),
            tooltip=["기간", alt.Tooltip("share", format=".1%")])
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=340),
                        use_container_width=True)

    # ---- 그 기간의 앨범 순위
    keys = sorted(src["기간"].unique(), reverse=True)
    if unit == "누적 (전체 기간)":
        sel = keys[0]
        sub("YG PLUS 가 유통한 앨범 — 누적 상위", f"써클 월간 톱100 누적 합 · {am['month'].min()} ~ {am['month'].max()}")
    else:
        c1_, c2_ = st.columns([2, 1])
        with c1_:
            sel = st.selectbox(f"{unit} 선택", keys, index=0, format_func=lambda k: lab.get(k, k), key="yp_period")
        sub(f"{lab.get(sel, sel)} — 유통 앨범 순위", "그 기간에 잡힌 출하량 기준")
    cur = src[src["기간"] == sel].groupby(["artist", "album"], as_index=False)["units"].sum()
    cur = cur.sort_values("units", ascending=False)
    n = st.slider("몇 개까지", 5, 100, min(30, max(5, len(cur))), 5, key="yp_top")
    t2 = cur.head(n).copy()
    t2["표시"] = t2["artist"].str.slice(0, 18) + " · " + t2["album"].str.slice(0, 30)
    st.altair_chart(alt.Chart(t2).mark_bar(color=C_BAR).encode(
        y=alt.Y("표시:N", sort="-x", title=None), x=alt.X("units:Q", title="물량 (장)"),
        tooltip=["artist", "album", alt.Tooltip("units", title="장", format=",.0f")]
    ).properties(height=26 * len(t2) + 40), use_container_width=True)
    st.caption(f"{lab.get(sel, sel)} 합계 {cur['units'].sum():,.0f}장 · 앨범 {len(cur)}종. "
               "하이브 소속 아티스트도 많습니다 — YG PLUS 는 남의 음악도 유통하기 때문입니다. "
               "2025-09 하이브 지분 매각 이후 이 물량이 빠지는지가 관전 포인트입니다.")
    with st.expander("표로 보기 · 내려받기"):
        st.dataframe(cur.rename(columns={"artist": "아티스트", "album": "앨범", "units": "물량(장)"}),
                     hide_index=True, use_container_width=True,
                     column_config={"물량(장)": st.column_config.NumberColumn(format="%,.0f")})
