# -*- coding: utf-8 -*-
"""오아시스 × 토스 신선식품 트래커 — 지어소프트(051160) 자회사 오아시스가 토스쇼핑 전용관(2026-09-17) 이후
잘 되는지, 공개 데이터 4개로 매주 본다. 경쟁사(컬리·쿠팡·SSG·이마트몰·네이버 / 배민·쿠팡이츠·요기요)도 나란히.

데이터: data/oasis/ (oasis_update.py 가 매주 채움)
  reviews.csv  오아시스몰 베스트 상품 리뷰 수 → 주간 증가분 = 주문량 대리지표
  trends.csv   구글 트렌드 KR 주간 검색량 (12개월)
  apprank.csv  앱스토어 KR 쇼핑 / 음식및음료 무료 순위
  news.csv     구글뉴스 주간 기사
판정 기준 (PM 2026-10-29): 리뷰 증가율 YoY +15% & 검색량 9월 대비 +30% → 시너지 Base 유지, 둘 다 아니면 Bear.
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "oasis"
TOSS_DAY = "2026-09-17"
PAL = {"오아시스마켓": "#2a78d6", "컬리": "#b06fc9", "쿠팡 로켓프레시": "#eb6834", "토스쇼핑": "#3fb27f",
       "SSG": "#e8c15a", "배달의민족": "#4fb8c9", "쿠팡이츠": "#eb6834", "요기요": "#e05252",
       "오아시스": "#2a78d6", "쿠팡": "#eb6834", "이마트올": "#999", "이마트몰": "#e8c15a", "네이버": "#3fb27f",
       "배민": "#4fb8c9"}

st.set_page_config(page_title="오아시스 × 토스", page_icon="🥬", layout="wide")
from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("logi")

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


rev, tr, ap, nw = get("reviews.csv"), get("trends.csv"), get("apprank.csv"), get("news.csv")

st.title("🥬 오아시스 × 토스 — 신선식품 잘 되나")
st.caption("지어소프트(051160) 자회사 오아시스. 토스쇼핑 전용관 2026-09-17 오픈 + 토스 300억 증자(지분 2.3%, post-money 1.33조). "
           "실적(4Q26)보다 먼저 보이는 신호 4개를 매주 쌓음. 쉬운 말: 리뷰가 늘면 주문이 는 것.")

# ───────────────────────── 0. 한 줄 판정
c1, c2, c3, c4 = st.columns(4)
if rev is not None and len(rev):
    days = sorted(rev["date"].unique())
    tot = rev.groupby("date")["reviews"].sum()
    last = tot.iloc[-1]
    d_wk = (tot.iloc[-1] - tot.iloc[-2]) if len(tot) > 1 else None
    c1.metric("베스트 상품 리뷰 합계", f"{int(last):,}", f"{int(d_wk):+,} / 전회 대비" if d_wk is not None else "첫 수집 — 다음 주부터 증가분")
else:
    c1.metric("베스트 상품 리뷰 합계", "—", "reviews.csv 없음")
if tr is not None and len(tr):
    o = tr[(tr.keyword == "오아시스마켓") & (tr.group == "장보기")].sort_values("date")
    base = o[(o.date >= "2026-08-01") & (o.date < TOSS_DAY)]["value"].mean()
    post = o[o.date >= TOSS_DAY]["value"].mean()
    c2.metric("구글 검색 (토스 전 vs 후 평균)", f"{post:.1f}", f"{(post / base - 1):+.0%} vs 8~9월" if base else "")
if ap is not None and len(ap):
    a = ap[(ap.company == "오아시스") & (ap.genre == "쇼핑")].sort_values("date")
    if len(a):
        d_r = (a.iloc[-2]["rank"] - a.iloc[-1]["rank"]) if len(a) > 1 else None
        c3.metric("앱스토어 쇼핑 순위 (오아시스)", f"{int(a.iloc[-1]['rank'])}위",
                  f"{int(d_r):+d}계단" if d_r is not None else "첫 수집")
if nw is not None and len(nw):
    n7 = nw[nw["query"].isin(['"오아시스마켓"', "오아시스 토스쇼핑"])]
    c4.metric("최근 7일 오아시스 기사", f"{n7[n7.week == n7.week.max()].shape[0]}건")

st.info("판정 기준: 리뷰 증가율 YoY **+15%** 이고 검색량 9월 대비 **+30%** → 시너지 Base(전환율 3%) 유지. "
        "둘 다 안 움직이면 Key Drivers 전환율을 Bear(1%) 로. 지어소프트 모델 `Oasis_Toss` 시트와 짝.")

# ───────────────────────── 1. 리뷰
sub("1. 오아시스몰 베스트 상품 리뷰 수", "주문량 대리지표 — 토스에서 주문해도 리뷰는 여기로 쌓임")
if rev is None or not len(rev):
    st.warning("아직 데이터 없음. `python oasis_update.py` 실행.")
else:
    tot = rev.groupby("date", as_index=False)["reviews"].sum()
    tot["증가분"] = tot["reviews"].diff()
    colA, colB = st.columns([2, 3])
    with colA:
        st.altair_chart(alt.Chart(tot).mark_bar(color="#2a78d6").encode(
            x=alt.X("date:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("증가분:Q", title="주간 리뷰 증가 (건)"),
            tooltip=["date", alt.Tooltip("reviews", format=",.0f"), alt.Tooltip("증가분", format="+,.0f")]
        ).properties(height=260), use_container_width=True)
        st.caption("첫 주는 증가분이 없음. 베스트 목록이 바뀌면 합계가 흔들릴 수 있어 아래 상품별 표를 같이 볼 것.")
    with colB:
        latest = rev[rev.date == rev.date.max()].sort_values("rank")
        if rev.date.nunique() > 1:
            prev = rev[rev.date == sorted(rev.date.unique())[-2]].set_index("product_id")["reviews"]
            latest = latest.assign(전회=latest.product_id.map(prev))
            latest["증가"] = latest["reviews"] - latest["전회"]
        st.dataframe(latest[[c for c in ("rank", "name", "reviews", "증가") if c in latest.columns]]
                     .rename(columns={"rank": "베스트순위", "name": "상품", "reviews": "리뷰 수"}),
                     hide_index=True, height=260, use_container_width=True)

# ───────────────────────── 2. 검색량
sub("2. 구글 검색량 (KR, 주간)", "토스 전용관 오픈일에 점선. 0~100 상대값 — 같은 그룹 안에서만 비교")
if tr is not None and len(tr):
    tabs = st.tabs(["장보기 (오아시스·컬리·쿠팡·토스쇼핑·SSG)", "음식배달 (배민·쿠팡이츠·요기요 + 오아시스)"])
    for tab, grp in zip(tabs, ("장보기", "음식배달")):
        with tab:
            d = tr[tr.group == grp].copy()
            d["date"] = pd.to_datetime(d["date"])
            line = alt.Chart(d).mark_line(point=False).encode(
                x=alt.X("date:T", title=None), y=alt.Y("value:Q", title="검색량 (상대)"),
                color=alt.Color("keyword:N", title=None,
                                scale=alt.Scale(domain=list(d.keyword.unique()),
                                                range=[PAL.get(k, "#888") for k in d.keyword.unique()])),
                tooltip=["date:T", "keyword", "value"])
            rule = alt.Chart(pd.DataFrame({"x": [pd.Timestamp(TOSS_DAY)]})).mark_rule(
                color="#f2c744", strokeDash=[4, 4]).encode(x="x:T")
            st.altair_chart((line + rule).properties(height=300), use_container_width=True)
    st.caption("오아시스마켓은 검색량 자체가 작아(컬리의 1/5) 노이즈가 큼. 추세만 볼 것.")

# ───────────────────────── 3. 앱 순위
sub("3. 앱스토어 KR 무료 순위", "쇼핑 카테고리 TOP200 · 음식배달은 '음식및음료'. 낮을수록 좋음")
if ap is not None and len(ap):
    dates = sorted(ap["date"].unique())
    latest = ap[ap.date == dates[-1]].copy()
    if len(dates) > 1:
        prev = ap[ap.date == dates[-2]].set_index(["genre", "company"])["rank"]
        latest["전회"] = [prev.get((g, c)) for g, c in zip(latest.genre, latest.company)]
        latest["변동"] = latest["전회"] - latest["rank"]          # + 면 올라간 것
    colA, colB = st.columns(2)
    for col, genre in ((colA, "쇼핑"), (colB, "음식및음료")):
        d = latest[latest.genre == genre].sort_values("rank")
        if not len(d):
            continue
        d = d.assign(label=d["rank"].map(lambda r: f"{int(r)}위"),
                     color=d["company"].map(lambda c: "#2a78d6" if c == "오아시스" else "#6b7f99"))
        base = alt.Chart(d).encode(y=alt.Y("company:N", sort=list(d.company), title=None))
        bars = base.mark_bar().encode(
            x=alt.X("rank:Q", title="순위 (왼쪽이 좋음)", scale=alt.Scale(domain=[0, 200])),
            color=alt.Color("color:N", scale=None),
            tooltip=["company", "rank", "app"] + (["변동"] if "변동" in d.columns else []))
        txt = base.mark_text(align="left", dx=4, color="#ddd", fontSize=12).encode(x="rank:Q", text="label:N")
        col.altair_chart((bars + txt).properties(height=40 + 30 * len(d), title=f"{genre} — {dates[-1]}"),
                         use_container_width=True)
    if len(dates) > 1:
        sub("3-1. 순위 추이", "주 1회 점. 위로 갈수록 좋음")
        colA, colB = st.columns(2)
        for col, genre in ((colA, "쇼핑"), (colB, "음식및음료")):
            d = ap[ap.genre == genre].copy()
            d["date"] = pd.to_datetime(d["date"])
            ch = alt.Chart(d).mark_line(point=True).encode(
                x=alt.X("date:T", title=None), y=alt.Y("rank:Q", title="순위", scale=alt.Scale(reverse=True)),
                color=alt.Color("company:N", title=None), tooltip=["date:T", "company", "rank"]
            ).properties(height=240, title=genre)
            col.altair_chart(ch, use_container_width=True)
    else:
        st.caption("순위 추이 선은 2주차 데이터부터 나옵니다 (지금은 기준선 1개).")
    cols = ["genre", "company", "rank"] + (["변동"] if "변동" in latest.columns else []) + ["app"]
    st.dataframe(latest.sort_values(["genre", "rank"])[cols].rename(
        columns={"genre": "카테고리", "company": "회사", "rank": "순위", "app": "앱"}),
        hide_index=True, use_container_width=True, height=45 + 36 * len(latest))   # 스크롤 없이 전부 보이게

# ───────────────────────── 4. 뉴스
sub("4. 최근 기사 (구글뉴스, 7일)", "오아시스마켓 · 오아시스 토스쇼핑 · 컬리 새벽배송 · 토스쇼핑")
if nw is not None and len(nw):
    d = nw[nw.week == nw.week.max()].sort_values("date", ascending=False)
    for q, g in d.groupby("query", sort=False):
        with st.expander(f"{q}  ·  {len(g)}건", expanded=(q == '"오아시스마켓"')):
            for r in g.itertuples():
                st.markdown(f"- {r.date} · [{r.title}]({r.url}) <span style='color:#888'>({r.press})</span>",
                            unsafe_allow_html=True)

st.divider()
st.caption("수동 체크 (월 1회): 토스쇼핑 전용관 SKU 수(처음 7,000종)·품절 비율 · DART 오아시스 분기보고서(11월) 매출 YoY·판관비율. "
           "갱신: `python oasis_update.py` 후 git push.")
