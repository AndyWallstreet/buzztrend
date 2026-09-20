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
EXCL_TOTAL = {"잉글우드랩", "티앤엘"}   # 코스메카 연결 포함 · 의료기기 위주 → 합계 제외

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
    _esc = lambda t: str(t).replace("~", "\\~")      # '~' 두 개가 취소선으로 렌더되는 것 방지
    st.info(f"**수급 결론** — {_esc(concl['headline'])}")
    if concl.get("detail"):
        st.caption(_esc(concl["detail"]))
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
em = get("exports_monthly.csv")
cxq = get("odm_capex_q.csv")
brq = get("brand_revenue_q.csv")
bru = get("brand_revenue_unlisted.csv")
H_BIG, H_MID = 460, 420          # 차트 높이
Y0 = "2016"                      # 10년+ 시작 연도


def same_co_yoy(df, co, per, val):
    """같은 회사끼리만 비교한 합계 YoY (신규 상장으로 합계가 튀는 것 방지)."""
    pv = df.pivot_table(index=co, columns=per, values=val, aggfunc="sum")
    cols = sorted(pv.columns)
    out = {}
    for a, b in zip(cols[:-1], cols[1:]):
        both = pv[[a, b]].dropna()
        both = both[(both[a] > 0)]
        if len(both) and both[a].sum() > 0:
            out[b] = both[b].sum() / both[a].sum() - 1
    return out


def top_n(df, co, val, n=6, other="기타"):
    """범례 정리: 합계 상위 n개만 이름, 나머지는 '기타'."""
    rank = df.groupby(co)[val].sum().sort_values(ascending=False).index[:n]
    d = df.copy()
    rest = d[co].nunique() - n
    if rest > 0:
        d[co] = d[co].where(d[co].isin(rank), f"{other} ({rest}사)")
    return d.groupby([c for c in d.columns if c != val], as_index=False)[val].sum()


def half_label(date_s):
    return date_s.str[:4] + "-" + date_s.str[5:7].astype(int).map(lambda m: "1H" if m <= 6 else "2H")
sg = pd.concat([x for x in (get("supply_signals.csv"), get("demand_signals.csv")) if x is not None])     if any(x is not None for x in (get("supply_signals.csv"), get("demand_signals.csv"))) else None

# ---- 공통 파생
odm_ann = odm_h1 = None
if oq is not None:
    oq = oq.copy()
    oq["year"] = oq["date"].astype(str).str[:4]
    odm_ann = oq.groupby(["co", "year"])["rev_eok"].sum().reset_index()
    tot = odm_ann[~odm_ann["co"].isin(EXCL_TOTAL)].groupby("year")["rev_eok"].sum()   # 코스메카 연결에 포함
    odm_tot = pd.DataFrame({"year": tot.index, "rev": tot.values})
    odm_tot["yoy"] = odm_tot["rev"].pct_change()
    h1 = oq[oq["q"].str.endswith(("Q1", "Q2"))].groupby(["co", "year"])["rev_eok"].sum().unstack("year")
    odm_h1 = h1
if cx is not None:
    cx = cx.copy()
    cx["year"] = cx["year"].astype(str).str.replace("FY", "", regex=False)
    cx["year"] = cx["year"].where(~cx["year"].str.startswith("1H"), "2026H1")
    _cxa = cx[~cx["year"].str.endswith("H1") & ~cx["company"].isin(EXCL_TOTAL)]
    cx_yoy = same_co_yoy(_cxa, "company", "year", "capex_eok")
    if cxq is not None:                                   # 1H26 vs 1H25 (분기 현금흐름표)
        _q = cxq[~cxq["company"].isin(EXCL_TOTAL) & cxq["q"].str[-2:].isin(["Q1", "Q2"])].copy()
        _q["year"] = _q["q"].str[:4]
        _n = _q.groupby(["company", "year"])["q"].nunique().reset_index(name="n")
        _q = _q.merge(_n[_n["n"] == 2], on=["company", "year"])
        _h = same_co_yoy(_q, "company", "year", "capex_eok")
        if "2026" in _h:
            cx_yoy["2026"] = _h["2026"]
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
        for _, x in ea[ea["year"] > Y0].iterrows():
            v = x["yoy_ytd"] if x["year"] == ea["year"].max() else x["yoy"]
            rows.append({"year": x["year"], "지표": "수요① 수출 YoY (관세청)", "value": v})
    if oq is not None:
        _oy = same_co_yoy(odm_ann[~odm_ann["co"].isin(EXCL_TOTAL)], "co", "year", "rev_eok")
        for y, v in _oy.items():
            if Y0 < y < oq["date"].max()[:4]:
                rows.append({"year": y, "지표": "수요② ODM 매출 YoY (실현)", "value": v})
        if odm_h1 is not None and "2025" in odm_h1.columns and "2026" in odm_h1.columns:
            _h = odm_h1.drop(index=list(EXCL_TOTAL), errors="ignore")
            v = _h["2026"].sum() / _h["2025"].sum() - 1
            rows.append({"year": "2026", "지표": "수요② ODM 매출 YoY (실현)", "value": v})
    if cx is not None:
        for y, v in cx_yoy.items():
            if y > Y0:
                rows.append({"year": y, "지표": "공급 Capex YoY (상장 ODM)", "value": v})
    if brq is not None:
        _b = brq[brq["type"] == "brand"].copy()
        _b["year"] = _b["date"].astype(str).str[:4]
        _ly = _b["year"].max()
        _by = same_co_yoy(_b[_b["year"] < _ly], "co", "year", "rev_eok")
        _bh = _b[_b["q"].str[-2:].isin(["Q1", "Q2"])]
        _by[_ly] = same_co_yoy(_bh, "co", "year", "rev_eok").get(_ly)
        for y, v in _by.items():
            if y > Y0 and v is not None:
                rows.append({"year": y, "지표": "수요③ 브랜드 매출 YoY (상장 18사)", "value": v})
    if rows:
        b = pd.DataFrame(rows).dropna()
        ch = alt.Chart(b).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="지표:N",
            y=alt.Y("value:Q", title="전년 대비 (%)", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[-0.4, 1.2], clamp=True)),
            color=alt.Color("지표:N", title=None,
                            scale=alt.Scale(domain=["수요① 수출 YoY (관세청)", "수요② ODM 매출 YoY (실현)",
                                                    "수요③ 브랜드 매출 YoY (상장 18사)", "공급 Capex YoY (상장 ODM)"],
                                            range=[C_BAR, "#8ec9ff", "#4fb8c9", C_LINE]),
                            legend=alt.Legend(orient="top")),
            tooltip=["year", "지표", alt.Tooltip("value", format="+.1%")])
        st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
        st.caption("**읽는법**: 파란 계열(수요)이 주황(공급 투자)보다 계속 높으면 공장이 수요를 못 따라간다 = 공급 부족. "
                   "주황이 파랑을 넘어서면 1\\~2년 뒤 공급 과잉 위험. **2026 = 수출은 8월 누적, 매출·Capex는 상반기(1H26 vs 1H25)**. "
                   "YoY는 두 해 모두 숫자가 있는 회사끼리만 비교(신규 상장 왜곡 제거). 축은 −40%\\~+120%에서 자름.")
    # ---- 반기별 : 1H26 까지
    hrows = []
    if em is not None:
        m = em.copy()
        m["half"] = half_label(m["month"].astype(str) + "-01")
        hm = m.groupby("half").agg(v=("exports_usd_bn", "sum"), n=("month", "count"))
        hm = hm[hm["n"] == 6]
        for h, v in hm["v"].pct_change(2).dropna().items():
            hrows.append({"half": h, "지표": "수요① 수출", "value": v})
    for df_, val_, name_ in ((oq, "rev_eok", "수요② ODM 매출"),
                             (brq[brq["type"] == "brand"] if brq is not None else None, "rev_eok", "수요③ 브랜드 매출"),
                             (cxq.rename(columns={"company": "co"}) if cxq is not None else None, "capex_eok", "공급 Capex")):
        if df_ is None:
            continue
        d_ = df_[~df_["co"].isin(EXCL_TOTAL)].copy()
        d_["half"] = half_label(d_["date"].astype(str))
        n_ = d_.groupby(["co", "half"])["q"].nunique().reset_index(name="n")
        d_ = d_.merge(n_[n_["n"] == 2], on=["co", "half"])
        pv_ = d_.pivot_table(index="co", columns="half", values=val_, aggfunc="sum")
        for h in pv_.columns:
            prev = f"{int(h[:4]) - 1}{h[4:]}"
            if prev in pv_.columns:
                both = pv_[[prev, h]].dropna()
                both = both[both[prev] > 0]
                if len(both):
                    hrows.append({"half": h, "지표": name_, "value": both[h].sum() / both[prev].sum() - 1})
    if hrows:
        sub("반기별 — 전년 같은 반기 대비", "1H26 까지 · 분기 공시(DART)·월별 관세청")
        hb = pd.DataFrame(hrows)
        hb = hb[hb["half"] >= "2018-1H"]
        ch = alt.Chart(hb).mark_line(point=True, size=2.5).encode(
            x=alt.X("half:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("value:Q", title="전년 동기 대비 (%)", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[-0.5, 1.5], clamp=True)),
            color=alt.Color("지표:N", title=None, scale=alt.Scale(domain=["수요① 수출", "수요② ODM 매출", "수요③ 브랜드 매출", "공급 Capex"],
                                                                 range=[C_BAR, "#8ec9ff", "#4fb8c9", C_LINE]), legend=alt.Legend(orient="top")),
            tooltip=["half", "지표", alt.Tooltip("value", format="+.1%")])
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#667").encode(y="y")
        st.altair_chart((zero + ch).properties(height=H_MID), use_container_width=True)
        st.caption("Capex 분기 자료는 2021년부터라 YoY는 2022-1H부터. 주황선(Capex)이 파란선(수요)을 크게 넘으면 증설 사이클 시작 신호.")
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
               "씨앤씨인터내셔널": "합계", "한국화장품제조": "화장품(음성공장)", "잉글우드랩": "제품",
               "엔에프씨": "충진/포장", "제닉": "하이드로겔 마스크류", "뷰티스킨": "기초화장품(제2공장)",
                 "선진뷰티사이언스": "안산-마이크로비드", "라파스": "마이크로니들패치-코스메틱", "아이큐어": "화장품(완주)",
                 "코스나인": "화장품(김포)", "나우코스": "세종공장(전사)", "본느": "전사", "씨티케이": "전사", "티앤엘": "전사"}
        rep = c[c.apply(lambda x: str(x["scope"]) == REP.get(x["company"], "전사"), axis=1)]
        rep = rep.sort_values("period").drop_duplicates(["company", "period"])
        BIG6 = ["코스맥스", "한국콜마", "코스메카코리아", "씨앤씨인터내셔널", "한국화장품제조", "엔에프씨"]
        allco = sorted(rep["company"].unique())
        pick = st.multiselect("회사 선택 (기본 = 완제품 ODM 6사)", allco,
                              default=[c_ for c_ in BIG6 if c_ in allco], key="sd_util_pick")
        rep = rep[rep["company"].isin(pick)] if pick else rep
        ch = alt.Chart(rep).mark_line(point=True, size=2).encode(
            x=alt.X("period:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("util:Q", title="가동률 (%)", scale=alt.Scale(domain=[0, 150], clamp=True)),
            color=alt.Color("company:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["company", "period", "scope", alt.Tooltip("util", format=".1f"), "unit"])
        rule = alt.Chart(pd.DataFrame({"y": [90]})).mark_rule(color=C_GOLD, strokeDash=[4, 3]).encode(y="y")
        st.altair_chart((ch + rule).properties(height=H_BIG), use_container_width=True)
        st.caption("한국 공장 기준. 금색 점선 = 90%. H1 = 상반기 연환산(계산). DART 생산능력은 3교대·이론치(명목)라 "
                   "실제 가동보다 낮게 나옴 — 회사끼리 높낮이보다 각 회사의 방향(오르는지)을 볼 것. 코스메카는 가동률 미공시라 계산값. 축은 150%에서 자름(티앤엘 2021 등 명목캐파 초과분).")
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
        sub("Capex — 유형자산 취득 (억원, DART 현금흐름표)", "2015\\~ · 마지막 막대 = 1H26(상반기만) · 회사별은 표")
        _c = cx[~cx["company"].isin(EXCL_TOTAL)][["company", "year", "capex_eok"]].copy()
        _c["year"] = _c["year"].str.replace("2026H1", "1H26")
        _c = top_n(_c, "company", "capex_eok", 6)
        ch = alt.Chart(_c).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0),
                    sort=sorted(_c["year"].unique(), key=lambda y: ("H" in y, y))),
            y=alt.Y("capex_eok:Q", title="억원", stack=True),
            color=alt.Color("company:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["company", "year", alt.Tooltip("capex_eok", format=",.0f")])
        st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
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
            d = ea[ea["year"] >= Y0].copy()
            last = d["year"].max()
            d["label"] = d["year"].where(d["year"] != last, last + " (누적)")
            d["v"] = d["exports_usd_bn"].where(d["year"] != last, d[ycol])
            ch = alt.Chart(d).mark_bar(color=C_BAR).encode(
                x=alt.X("label:O", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("v:Q", title="US$ bn"),
                tooltip=["label", alt.Tooltip("v", format=".2f")])
            st.altair_chart(ch.properties(height=H_MID), use_container_width=True)
        with c2:
            sub("수출 YoY", f"마지막 해는 {ycol.replace('ytd_to_m', '').replace('_usd_bn', '')}월 누적 기준")
            d2 = ea[ea["year"] > Y0].copy()
            d2["v"] = d2["yoy"].where(d2["year"] != last, d2["yoy_ytd"])
            st.altair_chart(yoy_chart(d2, "year", "v", C_LINE, "YoY").properties(height=H_MID), use_container_width=True)
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
        st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
        st.caption("마지막 해 = 1\\~8월 누적.")
    if oq is not None:
        sub("ODM 연결 매출 = 실현된 수요 (억원)", "DART 분기 합 · 마지막 해는 상반기")
        _o = odm_ann[(odm_ann["year"] >= Y0) & ~odm_ann["co"].isin(EXCL_TOTAL)].copy()
        _o["year"] = _o["year"].where(_o["year"] != _o["year"].max(), _o["year"].max() + " (상반기)")
        ch = alt.Chart(top_n(_o, "co", "rev_eok", 6)).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("rev_eok:Q", title="억원", stack=True),
            color=alt.Color("co:N", title=None, scale=alt.Scale(range=PAL), legend=alt.Legend(orient="top")),
            tooltip=["co", "year", alt.Tooltip("rev_eok", format=",.0f")])
        st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
        if odm_h1 is not None and "2025" in odm_h1.columns and "2026" in odm_h1.columns:
            t = odm_h1[["2025", "2026"]].copy()
            t["1H26 YoY"] = t["2026"] / t["2025"] - 1
            t.columns = ["1H25 (억원)", "1H26 (억원)", "1H26 YoY"]
            st.dataframe(t.round(3).style.format({"1H25 (억원)": "{:,.0f}", "1H26 (억원)": "{:,.0f}", "1H26 YoY": "{:+.1%}"}),
                         use_container_width=True)
    if brq is not None:
        b = brq.copy()
        b["year"] = b["date"].astype(str).str[:4]
        ly = b["year"].max()
        ba = b.groupby(["co", "type", "year"])["rev_eok"].sum().reset_index()
        ba["year"] = ba["year"].where(ba["year"] != ly, ly + " (상반기)")
        BIG2 = ["아모레퍼시픽", "LG생활건강"]
        sub("브랜드사 매출 — 상장 (억원, DART 연결)", "왼쪽 = 대형 2사 · 오른쪽 = 인디·중소 브랜드 (축이 다름)")
        c1, c2 = st.columns(2, gap="large")
        for col_, d_, n_ in ((c1, ba[ba["co"].isin(BIG2)], 2),
                             (c2, ba[~ba["co"].isin(BIG2) & (ba["type"] == "brand")], 7)):
            with col_:
                ch = alt.Chart(top_n(d_[["co", "year", "rev_eok"]], "co", "rev_eok", n_)).mark_bar().encode(
                    x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=-40)),
                    y=alt.Y("rev_eok:Q", title="억원", stack=True),
                    color=alt.Color("co:N", title=None, scale=alt.Scale(range=PAL + ["#5f7089"]), legend=alt.Legend(orient="top", columns=4)),
                    tooltip=["co", "year", alt.Tooltip("rev_eok", format=",.0f")])
                st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
        st.caption("LG생활건강은 생활용품·음료 포함 전사 매출, 애경산업도 생활용품 포함 — 화장품만의 숫자가 아님. "
                   "대형 2사는 자체 공장 비중이 커서 ODM 수요와 연결이 약하고, **오른쪽 인디 브랜드 매출이 ODM 주문의 직접 원천**.")
        h = b[b["q"].str[-2:].isin(["Q1", "Q2"])].groupby(["co", "type", "year"]).agg(rev=("rev_eok", "sum"), n=("q", "nunique")).reset_index()
        h = h[h["n"] == 2].pivot_table(index=["co", "type"], columns="year", values="rev")
        fy = b[b["year"] < ly].groupby(["co", "year"])["rev_eok"].sum().unstack("year")
        py = str(int(ly) - 1)
        if ly in h.columns and py in h.columns:
            cos = h.index.get_level_values("co")
            t = pd.DataFrame({"구분": h.index.get_level_values("type"), f"{py} 연간": fy[py].reindex(cos).values,
                              f"1H{py[2:]}": h[py].values, f"1H{ly[2:]}": h[ly].values}, index=cos)
            yc = f"1H{ly[2:]} YoY"
            t[yc] = t[f"1H{ly[2:]}"] / t[f"1H{py[2:]}"] - 1
            t = t.sort_values(f"1H{ly[2:]}", ascending=False)
            fmt = {c: "{:,.0f}" for c in t.columns if c not in ("구분", yc)}
            fmt[yc] = "{:+.1%}"
            st.dataframe(t.style.format(fmt, na_rep="—"), use_container_width=True, height=38 * (len(t) + 1))
    if bru is not None and len(bru):
        sub("브랜드사 매출 — 비상장 인디 (억원, DART 감사보고서)", "연간만 공시 · 구다이글로벌은 별도(자회사 이중계산 방지)")
        u = bru[bru["type"] == "brand"].copy() if "type" in bru.columns else bru.copy()
        u["year"] = u["year"].astype(str)
        ch = alt.Chart(top_n(u[["company", "year", "rev_eok"]].dropna(), "company", "rev_eok", 7)).mark_bar().encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("rev_eok:Q", title="억원", stack=True),
            color=alt.Color("company:N", title=None, scale=alt.Scale(range=PAL + ["#5f7089"]), legend=alt.Legend(orient="top")),
            tooltip=["company", "year", alt.Tooltip("rev_eok", format=",.0f")])
        st.altair_chart(ch.properties(height=H_BIG), use_container_width=True)
        pvu = u.pivot_table(index="company", columns="year", values="rev_eok", aggfunc="sum")
        st.dataframe(pvu.sort_values(pvu.columns[-1], ascending=False).style.format("{:,.0f}", na_rep="—"), use_container_width=True)
    if dm is not None and len(dm):
        sub("브랜드 수 · 생산실적 · 인디 브랜드 매출 (리서치)", "식약처·DART·언론")
        for s_name, g in dm.groupby("series"):
            g = g.sort_values("year")
            st.markdown(f"**{s_name}** ({g['unit'].iloc[0] if 'unit' in g else ''}) — " +
                        " · ".join(f"{y}: {v}" for y, v in zip(g["year"], g["value"])))
        st.caption("출처는 워크북 Demand 시트 D표 각 행 URL 참조.")
