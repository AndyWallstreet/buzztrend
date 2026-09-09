# -*- coding: utf-8 -*-
"""Cosmetics / Beauty 섹터 — 동국제약 센텔리안24 미국 수요 트래커.

- 구글 트렌드(미국): 자동 일일 수집 (cosmetics_update.py, 일배치 포함)
- 아마존: 약관상 자동 수집 금지(kbeauty/docs/ACCESS_REVIEW.md) →
  수동 스냅샷(manual_amazon.csv) + Keepa API 구독 시 자동화 가능
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"

st.set_page_config(page_title="Cosmetics/Beauty", page_icon="💄", layout="wide")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 0.97rem; font-weight: 700; background: #16283e;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 6px 12px; margin: 0.9rem 0 0.5rem 0;
}
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
    if not p.exists():
        return None
    return pd.read_csv(p)


st.title("Cosmetics / Beauty")
meta = {}
if (DATA / "gtrends_meta.json").exists():
    meta = json.loads((DATA / "gtrends_meta.json").read_text(encoding="utf-8"))
st.caption("화장품·뷰티 섹터 추적 — 1호: 동국제약(086450) 센텔리안24 미국 수요 · "
           f"구글 트렌드 갱신 {meta.get('fetched', '—')[:10]} (매일 07:20 배치) · "
           "[📋 동국제약 Stock Picker](/종목상세?ticker=A086450)")

# ---------------------------------------------------------------- 구글 트렌드
solo = load("gtrends_solo.csv", _stamp("gtrends_solo.csv"))
comp = load("gtrends_compare.csv", _stamp("gtrends_compare.csv"))

if solo is not None and len(solo):
    sp = solo.pivot_table(index="date", columns="keyword", values="value")
    cur = sp.iloc[-1]
    peak_m = sp["madeca cream"].max()
    m1, m2, m3 = st.columns(3)
    m1.metric("'madeca cream' 미국 검색 관심도 (최신 주)",
              f"{cur.get('madeca cream', 0):.0f}",
              f"12개월 최고 {peak_m:.0f} 대비 "
              f"{cur.get('madeca cream', 0) / peak_m * 100:.0f}% 수준",
              delta_color="off")
    m2.metric("'centellian24' (브랜드명)", f"{cur.get('centellian24', 0):.0f}",
              "제품명 검색이 브랜드명보다 훨씬 큼", delta_color="off")
    _m4 = sp["madeca cream"].tail(4).mean()
    _m4p = sp["madeca cream"].iloc[-8:-4].mean()
    m3.metric("최근 4주 평균 vs 직전 4주",
              f"{_m4:.0f} vs {_m4p:.0f}",
              f"{(_m4 / _m4p - 1) * 100:+.0f}%" if _m4p else None)

g1, g2 = st.columns(2, gap="large")
with g1:
    sub("센텔리안24 미국 검색 추세", "구글 트렌드 · 주간 · 12개월 롤링 (상대값, 최고=100)")
    if solo is not None and len(solo):
        d = solo.copy()
        d["date"] = pd.to_datetime(d["date"])
        ch = alt.Chart(d).mark_line(size=2.5, point=True).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("value:Q", title="검색 관심도 (상대값)"),
            color=alt.Color("keyword:N", title=None,
                            scale=alt.Scale(domain=["madeca cream", "centellian24"],
                                            range=[C_LINE, C_BAR]),
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("date:T"), "value"])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        st.caption("**읽는법**: 미국 소비자는 브랜드명(centellian24)보다 제품명(madeca "
                   "cream)으로 검색함 — 주황 선이 실수요 프록시. 이 선이 오르는데 "
                   "주가가 빠지면 수요-주가 괴리 구간. 아마존 판매의 선행/동행 지표.")
    else:
        st.info("아직 데이터가 없습니다 — python cosmetics_update.py 실행.")
with g2:
    sub("K뷰티 브랜드 검색 점유 비교", "같은 스케일 상대 비교 · 미국")
    if comp is not None and len(comp):
        d = comp.copy()
        d["date"] = pd.to_datetime(d["date"])
        ch = alt.Chart(d).mark_line(size=2).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("value:Q", title="검색 관심도 (상대값)"),
            color=alt.Color("keyword:N", title=None,
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("date:T"), "value"])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        st.caption("**읽는법**: anua·medicube·cosrx 같은 대형 K뷰티 인디 브랜드 대비 "
                   "센텔리안24의 미국 인지도 위치. 격차가 좁혀지는지가 아마존 채널 "
                   "성장 여력의 가늠자.")

# ---------------------------------------------------------------- 아마존
sub("아마존 스냅샷 — 센텔리안24 (수동 확인)",
    "자동 스크래핑은 아마존 약관 위반이라 하지 않음 · 주 1회 눈으로 확인해 기록")
am = load("manual_amazon.csv", _stamp("manual_amazon.csv"))
if am is not None and len(am):
    last_d = am["date"].max()
    cur = am[am["date"] == last_d].copy()
    hero = cur.sort_values("bought_last_month", ascending=False).iloc[0]
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("히어로 제품 월 구매", f"{hero['bought_last_month']:,.0f}+",
              str(hero["product"])[:22], delta_color="off")
    a2.metric("평점", f"{hero['rating']}★", f"리뷰 {hero['reviews']:,.0f}개",
              delta_color="off")
    _low = cur[cur["note"].astype(str).str.contains("재고", na=False)]
    a3.metric("재고 부족 표시 제품", f"{len(_low)}개",
              "'재고 N개' 표시 = 수요>공급 신호", delta_color="off")
    a4.metric("스냅샷 기준일", last_d, "다음 확인: 주 1회 권장", delta_color="off")

    view = cur[["product", "rating", "reviews", "bought_last_month",
                "price_krw", "note"]].copy()
    view.columns = ["제품", "평점", "리뷰 수", "월 구매(개+)", "표시 가격(원)", "비고"]
    st.dataframe(view, hide_index=True, use_container_width=True)
    st.caption("**읽는법**: '월 구매'는 아마존이 표시하는 '지난달 구매횟수' — 리뷰 "
               "증가 속도보다 빠른 수요 지표. 여러 날짜가 쌓이면 아래 추이 차트가 "
               "생김. 가격은 한국 IP 기준 원화 표시.")
    if am["date"].nunique() >= 2:
        sub("아마존 지표 추이", "스냅샷이 쌓일수록 촘촘해짐")
        tr = am.copy()
        tr["date"] = pd.to_datetime(tr["date"])
        ch = alt.Chart(tr).mark_line(size=2, point=True).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("bought_last_month:Q", title="월 구매 (개+)"),
            color=alt.Color("product:N", title=None,
                            legend=alt.Legend(orient="top", labelLimit=220)),
            tooltip=["product", alt.Tooltip("date:T"),
                     alt.Tooltip("bought_last_month", format=",.0f")])
        st.altair_chart(ch.properties(height=280), use_container_width=True)

# ------------------------------------------------- 아마존 인기도 워치 (Top 30)
aw = load("amazon_watch.csv", _stamp("amazon_watch.csv"))
if aw is not None and len(aw):
    sub("아마존 인기도 워치 — 페이셜 크림·모이스처라이저 Top 30",
        "베스트셀러 리스트 + 각 제품 상세페이지 · 수동 스냅샷")
    dates = sorted(aw["date"].unique())
    cur = aw[aw["date"] == dates[-1]].copy()
    prev = aw[aw["date"] == dates[-2]].copy() if len(dates) >= 2 else None

    kbn = int((cur["kbeauty"] == 1).sum())
    ct = cur[cur["brand"] == "CENTELLIAN 24"]
    w1, w2, w3 = st.columns(3)
    w1.metric("Top 30 중 K뷰티 제품", f"{kbn}개",
              "실리콘투 등 K뷰티 수출주 방향 지표", delta_color="off")
    if len(ct):
        w2.metric("센텔리안24 순위", f"{int(ct['rank'].iloc[0])}위",
                  f"뷰티 전체 #{int(ct['bsr_beauty'].iloc[0])}", delta_color="off")
    _top_kb = cur[cur["kbeauty"] == 1].sort_values("rank").iloc[0]
    w3.metric(f"K뷰티 1위: {_top_kb['brand']}", f"{int(_top_kb['rank'])}위",
              (f"월 구매 {_top_kb['bought_month']:,.0f}+"
               if pd.notna(_top_kb["bought_month"]) else None),
              delta_color="off")

    # ---- 변화 요약 (직전 스냅샷 대비)
    if prev is not None:
        msgs = []
        m = cur.merge(prev[["asin", "rank", "rating", "bought_month"]],
                      on="asin", suffixes=("", "_p"))
        for _, r in m.sort_values("rank").iterrows():
            nm = r["brand"]
            if abs(r["rank"] - r["rank_p"]) >= 3:
                a = "▲" if r["rank"] < r["rank_p"] else "▼"
                msgs.append(f"{a} **{nm}** 순위 {int(r['rank_p'])}→{int(r['rank'])}위")
            if (pd.notna(r["rating"]) and pd.notna(r["rating_p"])
                    and abs(r["rating"] - r["rating_p"]) >= 0.1):
                msgs.append(f"**{nm}** 평점 {r['rating_p']}→{r['rating']}")
            if (pd.notna(r["bought_month"]) and pd.notna(r["bought_month_p"])
                    and r["bought_month"] != r["bought_month_p"]):
                msgs.append(f"**{nm}** 월 구매 {r['bought_month_p']:,.0f}+"
                            f"→{r['bought_month']:,.0f}+")
        for _, r in cur[~cur["asin"].isin(prev["asin"])].iterrows():
            msgs.append(f"🆕 **{r['brand']} {str(r['product'])[:16]}** "
                        f"Top 30 진입({int(r['rank'])}위)")
        for _, r in prev[~prev["asin"].isin(cur["asin"])].iterrows():
            msgs.append(f"⛔ **{r['brand']} {str(r['product'])[:16]}** Top 30 이탈")
        if msgs:
            st.markdown(f"**{dates[-2]} → {dates[-1]} 변화**: "
                        + " · ".join(msgs[:12]))
        else:
            st.caption(f"{dates[-2]} 대비 큰 변화 없음 (기준: 순위 ±3, 평점 ±0.1, "
                       "월 구매 구간 변동)")
    else:
        st.caption("첫 스냅샷 — 두 번째 갱신부터 이 자리에 '무엇이 오르고 내렸는지' "
                   "요약이 자동으로 붙습니다.")

    only_kb = st.toggle("K-Beauty만 보기", value=True, key="aw_kb")
    show = (cur[cur["kbeauty"] == 1] if only_kb else cur).sort_values("rank").copy()

    if prev is not None:
        pv = prev.set_index("asin")["rank"]

        def _delta(r):
            if r["asin"] not in pv.index:
                return "🆕"
            d = int(pv[r["asin"]] - r["rank"])
            return f"▲{d}" if d > 0 else (f"▼{-d}" if d < 0 else "＝")
        show["Δ"] = show.apply(_delta, axis=1)
    else:
        show["Δ"] = "—"
    show["할인%"] = (1 - show["price_krw"] / show["list_price_krw"]) * 100

    view = show[["rank", "Δ", "brand", "product", "price_krw", "list_price_krw",
                 "할인%", "rating", "reviews", "bought_month", "bsr_beauty",
                 "bsr_sub", "sub_note", "note"]].copy()
    view.columns = ["순위", "Δ", "브랜드", "제품", "가격(원)", "정가(원)", "할인%",
                    "평점", "리뷰 수", "월 구매(개+)", "BSR 뷰티", "세부 순위",
                    "세부 카테고리", "비고"]
    for c, f in {"순위": "{:.0f}", "가격(원)": "{:,.0f}", "정가(원)": "{:,.0f}",
                 "할인%": "{:.0f}%", "평점": "{:.1f}", "리뷰 수": "{:,.0f}",
                 "월 구매(개+)": "{:,.0f}", "BSR 뷰티": "{:.0f}",
                 "세부 순위": "{:.0f}"}.items():
        view[c] = view[c].map(lambda v, f=f: f.format(v) if pd.notna(v) else "—")
    view = view.fillna("—")
    _hl = show["brand"].eq("CENTELLIAN 24").tolist()
    st.dataframe(
        view.style.apply(
            lambda r: ["background-color:#1e3a5c; color:#f2c744; font-weight:700"
                       if _hl[list(view.index).index(r.name)] else ""] * len(r),
            axis=1),
        hide_index=True, use_container_width=True,
        height=min(430, 40 + 35 * len(view)))
    st.caption("**읽는법**: 순위=아마존 '페이셜 크림·모이스처라이저' 베스트셀러(판매 "
               "속도 기준, 자주 갱신), Δ=직전 스냅샷 대비 이동. '월 구매'는 아마존 "
               "표시값(1천+, 5만+ 식 반올림). 배송지가 한국이라 일부 리스팅은 "
               "가격·월구매가 숨겨짐(비고 참조). 'Customers say' AI 요약은 로그인 "
               "화면에만 표시돼 아직 미수집. 실리콘투(257720) 프록시로 쓸 때는 "
               "브랜드별 유통 경로(직판 vs 수출대행)를 따로 확인할 것.")

    # ---- 월 구매 비교 차트 (K뷰티)
    kb = cur[(cur["kbeauty"] == 1) & cur["bought_month"].notna()].copy()
    if len(kb):
        kb["label"] = kb["brand"] + " " + kb["product"].str.slice(0, 14)
        kb["ctl"] = kb["brand"].eq("CENTELLIAN 24")
        base = alt.Chart(kb).encode(
            x=alt.X("bought_month:Q", title="월 구매 (개+, 아마존 표시값)"),
            y=alt.Y("label:N", sort="-x", title=None))
        bars = base.mark_bar().encode(
            color=alt.Color("ctl:N", legend=None,
                            scale=alt.Scale(domain=[False, True],
                                            range=[C_BAR, C_GOLD])))
        txt = base.mark_text(align="left", dx=4, color="#c6d0de").encode(
            text=alt.Text("bought_month:Q", format=",.0f"))
        st.altair_chart((bars + txt).properties(height=220),
                        use_container_width=True)
        st.caption("**읽는법**: 상세페이지에 '월 구매'가 표시된 K뷰티 제품만 비교. "
                   "Anua PDRN 크림 10만+ vs 센텔리안(금색 막대) 5만+ — 이 격차가 "
                   "줄어드는지가 핵심 관전 포인트.")

st.info("**갱신 방법** — ① 구글 트렌드: 매일 배치 자동. ② 아마존: 주 1회 "
        "amazon.com에서 'centellian24' 검색 → 각 제품의 평점·리뷰 수·'지난달 "
        "구매횟수'·가격을 `data/cosmetics/manual_amazon.csv`에 한 줄씩 추가 "
        "(제가 해드릴 수 있음 — '아마존 스냅샷 갱신해줘'라고 하면 됨). "
        "③ 자동화를 원하면 **Keepa API** (€49/월, 판매랭크·리뷰 이력 제공) 구독 — "
        "kbeauty 접근성 검토에서 권장했던 정식 경로.")

st.divider()
st.caption("데이터: 구글 트렌드(주간, 미국, 상대값) 자동 · 아마존 수동 스냅샷 "
           "(약관 준수). 검색 관심도는 판매량이 아니라 수요의 방향 지표.")
