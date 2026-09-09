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

# ------------------------------------------------------- 경쟁사 순위 (아마존 BSR)
cp = load("manual_amazon_competitors.csv", _stamp("manual_amazon_competitors.csv"))
if cp is not None and len(cp):
    sub("아마존 베스트셀러 순위 — K뷰티 경쟁 구도",
        "BSR(판매 속도 순위) · 카테고리별 · 수동 스냅샷")
    last_d = cp["date"].max()
    cc = cp[cp["date"] == last_d].copy()
    cc["_ctl"] = cc["brand"].eq("CENTELLIAN 24")
    cc = cc.sort_values(["rank_scope", "rank"])
    view = cc[["rank_scope", "rank", "brand", "product", "rating", "reviews",
               "bought_last_month", "price_krw", "note"]].copy()
    view.columns = ["카테고리", "순위", "브랜드", "제품", "평점", "리뷰 수",
                    "월 구매(개+)", "가격(원)", "비고"]
    _hl = cc["_ctl"].tolist()
    st.dataframe(
        view.style.apply(
            lambda r: ["background-color:#1e3a5c; color:#f2c744; font-weight:700"
                       if _hl[list(view.index).index(r.name)] else ""] * len(r),
            axis=1
        ).format({"순위": "{:.0f}", "평점": "{:.1f}", "리뷰 수": "{:,.0f}",
                  "월 구매(개+)": "{:,.0f}", "가격(원)": "{:,.0f}"},
                 na_rep="—"),
        hide_index=True, use_container_width=True)
    st.caption(f"**읽는법**: BSR은 아마존이 판매 속도로 매기는 순위(자주 갱신). "
               "센텔리안(강조 행)은 '페이셜 크림·모이스처라이저' #19, 세부 "
               "'페이스 모이스처라이저' #12 — Anua(#3)·medicube(#7)가 크림에서 "
               "앞서 있고, medicube 토너패드·BIODANCE 마스크는 뷰티 전체 2·3위로 "
               "월 10만+개 팔림(센텔리안 히어로는 5만+). 순위가 주 단위로 오르는지가 "
               f"핵심. 기준일 {last_d}.")

st.info("**갱신 방법** — ① 구글 트렌드: 매일 배치 자동. ② 아마존: 주 1회 "
        "amazon.com에서 'centellian24' 검색 → 각 제품의 평점·리뷰 수·'지난달 "
        "구매횟수'·가격을 `data/cosmetics/manual_amazon.csv`에 한 줄씩 추가 "
        "(제가 해드릴 수 있음 — '아마존 스냅샷 갱신해줘'라고 하면 됨). "
        "③ 자동화를 원하면 **Keepa API** (€49/월, 판매랭크·리뷰 이력 제공) 구독 — "
        "kbeauty 접근성 검토에서 권장했던 정식 경로.")

st.divider()
st.caption("데이터: 구글 트렌드(주간, 미국, 상대값) 자동 · 아마존 수동 스냅샷 "
           "(약관 준수). 검색 관심도는 판매량이 아니라 수요의 방향 지표.")
