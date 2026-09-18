# -*- coding: utf-8 -*-
"""화장품 ODM/OEM 수급 트래커 — 공급(생산능력·가동률·증설·Capex) vs 수요(수출·브랜드·ODM 매출).

원본은 ~/cosmetics-sd 워크북 (화장품_수급_Tracker_vXX.xlsx). build_workbook.py 가 같은
CSV를 data/cosmetics_sd/ 에 복사하므로 이 페이지와 엑셀은 항상 같은 숫자를 보여준다.
결론 문장은 data/cosmetics_sd/conclusion.json (사람이 씀).
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics_sd"
C_BAR, C_LINE, C_GOLD, C_RED, C_GREEN = "#2a78d6", "#eb6834", "#e8c15a", "#e05252", "#3fb27f"
PAL = ["#2a78d6", "#eb6834", "#4fb8c9", "#b06fc9", "#8ec9ff", "#e8c15a", "#3fb27f"]

st.set_page_config(page_title="화장품 ODM 수급", page_icon="⚖️", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("beauty")

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
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


def get(name):
    return load(name, _stamp(name))


def yoy_chart(df, xcol, ycol, color, title_y, fmt="%"):
    base = alt.Chart(df).encode(x=alt.X(f"{xcol}:O", title=None, axis=alt.Axis(labelAngle=0)))
    bars = base.mark_bar(color=color).encode(
        y=alt.Y(f"{ycol}:Q", title=title_y, axis=alt.Axis(format=fmt)),
        tooltip=[xcol, alt.Tooltip(ycol, format=".1%" if fmt == "%" else ",.0f")])
    txt = base.mark_text(dy=-8, fontSize=11, color="#ddd").encode(
        y=f"{ycol}:Q", text=alt.Text(f"{ycol}:Q", format="+.0%" if fmt == "%" else ",.0f"))
    return bars + txt


st.title("화장품 ODM/OEM 수급 트래커")
concl = {}
if (DATA / "conclusion.json").exists():
    concl = json.loads((DATA / "conclusion.json").read_text(encoding="utf-8"))
st.caption("공급 = ODM 생산능력·가동률·증설·Capex (DART 공시) · 수요 = 화장품 수출(관세청)·브랜드 매출·ODM 실현 매출 · "
           f"갱신 {concl.get('asof', '—')} · 원본 엑셀: Companies/화장품/화장품_수급_Tracker")

if concl.get("headline"):
    st.info(f"**수급 결론** — {concl['headline']}")
    if concl.get("detail"):
        st.caption(concl["detail"])
else:
    st.warning("결론 문장이 아직 없습니다 (data/cosmetics_sd/conclusion.json).")

tab_bal, tab_sup, tab_dem = st.tabs(["⚖️ 수급 판단", "🏭 공급 (ODM)", "🛒 수요 (브랜드·수출)"])

ea = get("exports_annual.csv")
er = get("exports_region.csv")
oq = get("odm_revenue_q.csv")
cap = get("odm_capacity.csv")
cx = get("odm_capex.csv")
exp = get("odm_expansion.csv")
dm = get("demand.csv")
sg = pd.concat([x for x in (get("supply_signals.csv"), get("demand_signals.csv")) if x is not None])     if any(x is not None for x in (get("supply_signals.csv"), get("demand_signals.csv"))) else None

# ---- 공통 파생
odm_ann = odm_h1 = None
if oq is not None:
    oq = oq.copy()
    oq["year"] = oq["date"].astype(str).str[:4]
    odm_ann = oq.groupby(["co", "year"])["rev_eok"].sum().reset_index()
    tot = odm_ann[odm_ann["co"] != "잉글우드랩"].groupby("year")["rev_eok"].sum()   # 코스메카 연결에 포함
    odm_tot = pd.DataFrame({"year": tot.index, "rev": tot.values})
    odm_tot["yoy"] = odm_tot["rev"].pct_change()
    h1 = oq[oq["q"].str.endswith(("Q1", "Q2"))].groupby(["co", "year"])["rev_eok"].sum().unstack("year")
    odm_h1 = h1
if cx is not None:
    cx = cx.copy()
    cx["year"] = cx["year"].astype(str).str.replace("FY", "", regex=False)
    cx["year"] = cx["year"].where(~cx["year"].str.startswith("1H"), "2026H1")
    cx_tot = cx[~cx["year"].str.endswith("H1") & (cx["company"] != "잉글우드랩")].groupby("year")["capex_eok"].sum().reset_index()
    cx_tot["yoy"] = cx_tot["capex_eok"].pct_change()
if ea is not None:
    ea = ea.rename(columns={ea.columns[0]: "year"})
    ea["year"] = ea["year"].astype(str)
    ycol = [c for c in ea.columns if c.startswith("ytd")][0]
    ea["yoy"] = ea["exports_usd_bn"].pct_change()
    ea["yoy_ytd"] = ea[ycol].pct_change()

# ================================================================ 수급 판단
with tab_bal:
    sub("공급 증가율 vs 수요 증가율 — 같은 축", "수요: 수출 YoY·ODM 매출 YoY · 공급: Capex YoY·가동률")
    rows = []
    if ea is not None:
        for _, x in ea[ea["year"] >= "2021"].iterrows():
            v = x["yoy_ytd"] if x["year"] == ea["year"].max() else x["yoy"]
            rows.append({"year": x["year"], "지표": "수요① 수출 YoY (관세청)", "value": v})
    if oq is not None:
        for _, x in odm_tot[odm_tot["year"] >= "2021"].iterrows():
            if x["year"] < oq["date"].max()[:4]:
                rows.append({"year": x["year"], "지표": "수요② ODM 매출 YoY (실현)", "value": x["yoy"]})
        if odm_h1 is not None and "2025" in odm_h1.columns and "2026" in odm_h1.columns:
            _h = odm_h1.drop(index="잉글우드랩", errors="ignore")
            v = _h["2026"].sum() / _h["2025"].sum() - 1
            rows.append({"year": "2026", "지표": "수요② ODM 매출 YoY (실현)", "value": v})
    if cx is not None:
        for _, x in cx_tot[cx_tot["year"] >= "2021"].iterrows():
            rows.append({"year": x["year"], "지표": "공급② Capex YoY (ODM 5사)", "value": x["yoy"]})
    if rows:
        b = pd.DataFrame(rows).dropna()
        ch = alt.Chart(b).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="지표:N",
            y=alt.Y("value:Q", title="전년 대비 (%)", axis=alt.Axis(format="%")),
            color=alt.Color("지표:N", title=None,
                            scale=alt.Scale(domain=["수요① 수출 YoY (관세청)", "수요② ODM 매출 YoY (실현)", "공급② Capex YoY (ODM 5사)"],
                                            range=[C_BAR, "#8ec9ff", C_LINE]),
                            legend=alt.Legend(orient="top")),
            tooltip=["year", "지표", alt.Tooltip("value", format="+.1%")])
        st.altair_chart(ch.properties(height=330), use_container_width=True)
        st.caption("**읽는법**: 파란 막대(수요)가 주황(공급 투자)보다 계속 높으면 공장이 수요를 못 따라간다 = 공급 부족. "
                   "주황이 파랑을 넘어서면 1~2년 뒤 공급 과잉 위험. 2026 수요는 8월 누적, ODM 매출은 상반기 YoY.")
    if cap is not None and len(cap):
        sub("가동률 — 회사가 공시한 값", "DART 사업보고서 '생산설비' · 90% 넘게 유지되면 캐파 제약")
        c = cap.copy()
        c["period"] = c["period"].astype(str)
        half = c["period"].str.endswith("H1")
        ann_cap = c["basis"].astype(str).str.contains("연환산")
        calc = c["output"] / c["capacity"] * 100
        calc = calc.where(~(half & ann_cap), c["output"] * 2 / c["capacity"] * 100)   # 반기실적 x2 / 연환산 캐파
        c["util"] = pd.to_numeric(c["util_pct"], errors="coerce").fillna(calc)
        c = c[c["util"].notna()]
        REP = {"코스맥스": "한국", "한국콜마": "화장품 - 한국", "코스메카코리아": "한국",
               "씨앤씨인터내셔널": "합계", "한국화장품제조": "화장품(음성공장)", "잉글우드랩": "제품"}
        rep = c[c.apply(lambda x: str(x["scope"]) == REP.get(x["company"], "전사"), axis=1)]
        rep = rep.sort_values("period").drop_duplicates(["company", "period"])
        ch = alt.Chart(rep).mark_line(point=True, size=2).encode(
            x=alt.X("period:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("util:Q", title="가동률 (%)", scale=alt.Scale(zero=False)),
            color=alt.Color("company:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["company", "period", "scope", alt.Tooltip("util", format=".1f"), "unit"])
        rule = alt.Chart(pd.DataFrame({"y": [90]})).mark_rule(color=C_GOLD, strokeDash=[4, 3]).encode(y="y")
        st.altair_chart((ch + rule).properties(height=300), use_container_width=True)
        st.caption("한국 공장 기준. 금색 점선 = 90%. H1 = 상반기 연환산(계산). DART 생산능력은 3교대·이론치(명목)라 "
                   "실제 가동보다 낮게 나옴 — 회사끼리 높낮이보다 각 회사의 방향(오르는지)을 볼 것. 코스메카는 가동률 미공시라 계산값.")
    if sg is not None and len(sg):
        sub("수급 신호 (정성)", "tight = 수요>공급 · loose = 공급>수요")
        s = sg.sort_values("date", ascending=False).copy()
        s["방향"] = s["direction"].map(lambda d: "🔴 tight" if str(d).startswith("tight") else "🟢 loose" if str(d).startswith("loose") else str(d))
        st.dataframe(s[["date", "방향", "signal", "quote", "source"]].rename(
            columns={"date": "날짜", "signal": "신호", "quote": "인용", "source": "출처"}),
            hide_index=True, use_container_width=True)

# ================================================================ 공급
with tab_sup:
    if cap is not None and len(cap):
        sub("생산능력 · 생산실적 · 가동률 (회사 공시 단위 그대로)", "회사끼리 합산하지 말 것 — 단위가 다름")
        show = cap[["company", "period", "scope", "capacity", "output", "unit", "basis", "util_pct", "util_source", "note"]].rename(
            columns={"company": "회사", "period": "기간", "scope": "범위", "capacity": "생산능력", "output": "생산실적",
                     "unit": "단위", "basis": "기준", "util_pct": "가동률(%)", "util_source": "출처", "note": "비고"})
        st.dataframe(show.sort_values(["회사", "기간"]), hide_index=True, use_container_width=True,
                     column_config={"생산능력": st.column_config.NumberColumn(format="%,.0f"),
                                    "생산실적": st.column_config.NumberColumn(format="%,.0f"),
                                    "가동률(%)": st.column_config.NumberColumn(format="%.1f")})
    if cx is not None:
        sub("Capex — 유형자산 취득 (억원, DART 현금흐름표)", "합계 막대 · 회사별은 표")
        ch = alt.Chart(cx[~cx["year"].str.endswith("H1")]).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("capex_eok:Q", title="억원", stack=True),
            color=alt.Color("company:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["company", "year", alt.Tooltip("capex_eok", format=",.0f")])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        pv = cx.pivot_table(index="company", columns="year", values="capex_eok", aggfunc="sum")
        pv.columns = [c.replace("2026H1", "1H26") for c in pv.columns]
        st.dataframe(pv.round(0), use_container_width=True)
    if exp is not None and len(exp):
        sub("증설 파이프라인 — 2024~2028", "공시·IR·언론. 상태 = 계획/공사중/가동")
        cols = [c for c in ["company", "plant", "country", "announced", "start", "added_capacity", "capacity_unit",
                            "investment_eok", "status", "source"] if c in exp.columns]
        st.dataframe(exp[cols].rename(columns={
            "company": "회사", "plant": "공장", "country": "국가", "announced": "발표", "start": "가동",
            "added_capacity": "추가 캐파", "capacity_unit": "단위", "investment_eok": "투자(억원)", "status": "상태",
            "source": "출처"}), hide_index=True, use_container_width=True)

# ================================================================ 수요
with tab_dem:
    if ea is not None:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            sub("화장품 수출 — 연간 (US$ bn)", "관세청 HS 3303~3307")
            d = ea[ea["year"] >= "2019"].copy()
            last = d["year"].max()
            d["label"] = d["year"].where(d["year"] != last, last + " (누적)")
            d["v"] = d["exports_usd_bn"].where(d["year"] != last, d[ycol])
            ch = alt.Chart(d).mark_bar(color=C_BAR).encode(
                x=alt.X("label:O", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("v:Q", title="US$ bn"),
                tooltip=["label", alt.Tooltip("v", format=".2f")])
            st.altair_chart(ch.properties(height=280), use_container_width=True)
        with c2:
            sub("수출 YoY", f"마지막 해는 {ycol.replace('ytd_to_m', '').replace('_usd_bn', '')}월 누적 기준")
            d2 = ea[ea["year"] >= "2020"].copy()
            d2["v"] = d2["yoy"].where(d2["year"] != last, d2["yoy_ytd"])
            st.altair_chart(yoy_chart(d2, "year", "v", C_LINE, "YoY").properties(height=280), use_container_width=True)
    if er is not None:
        sub("수출 지역별 (US$ bn)", "Asia(중국 포함) 감소 · 북미·유럽 증가 = 필요한 공장 위치가 바뀜")
        e = er.rename(columns={er.columns[0]: "year"})
        e["year"] = e["year"].astype(str)
        long = e.melt("year", var_name="region", value_name="v")
        ch = alt.Chart(long).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("v:Q", title="US$ bn", stack=True),
            color=alt.Color("region:N", title=None, scale=alt.Scale(range=PAL + ["#5f7089", "#9aa"]), legend=alt.Legend(orient="top")),
            tooltip=["year", "region", alt.Tooltip("v", format=".2f")])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
    if oq is not None:
        sub("ODM 연결 매출 = 실현된 수요 (억원)", "DART 분기 합 · 마지막 해는 상반기")
        ch = alt.Chart(odm_ann[odm_ann["year"] >= "2019"]).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("rev_eok:Q", title="억원", stack=True),
            color=alt.Color("co:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["co", "year", alt.Tooltip("rev_eok", format=",.0f")])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        if odm_h1 is not None and "2025" in odm_h1.columns and "2026" in odm_h1.columns:
            t = odm_h1[["2025", "2026"]].copy()
            t["1H26 YoY"] = t["2026"] / t["2025"] - 1
            t.columns = ["1H25 (억원)", "1H26 (억원)", "1H26 YoY"]
            st.dataframe(t.round(3).style.format({"1H25 (억원)": "{:,.0f}", "1H26 (억원)": "{:,.0f}", "1H26 YoY": "{:+.1%}"}),
                         use_container_width=True)
    if dm is not None and len(dm):
        sub("브랜드 수 · 생산실적 · 인디 브랜드 매출 (리서치)", "식약처·DART·언론")
        for s_name, g in dm.groupby("series"):
            g = g.sort_values("year")
            st.markdown(f"**{s_name}** ({g['unit'].iloc[0] if 'unit' in g else ''}) — " +
                        " · ".join(f"{y}: {v}" for y, v in zip(g["year"], g["value"])))
        st.caption("출처는 워크북 Demand 시트 D표 각 행 URL 참조.")
