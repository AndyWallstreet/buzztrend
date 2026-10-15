# -*- coding: utf-8 -*-
"""Amazon Tracker — K뷰티 브랜드 아마존 판매순위(BSR) + 수요 퍼널 검증.

데이터 (data/cosmetics/):
    bsr_monthly.csv / bsr_monthly_jp.csv   python keepa_bsr_history.py [--domain 5]
    bsr_asins.csv / bsr_asins_jp.csv       브랜드별 대표 ASIN (제목 확인 완료)
    funnel_result.csv / funnel_by_brand.csv / funnel_panel.csv   python funnel_study.py
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics"
MKT = {"US": "미국 (amazon.com)", "JP": "일본 (amazon.co.jp)"}
C_US, C_JP = "#2a78d6", "#eb6834"
C_SEARCH, C_BSR, C_REV = "#8ec9ff", "#e8c15a", "#3fb27f"
# 앱을 열면 기본으로 보이는 브랜드 (PM 2026-10-15)
DEFAULT = ["cosrx", "reedle shot", "madeca cream", "medicube"]
FOCUS = DEFAULT + ["atopalm", "anua"]
# 'madeca cream' 은 다른 파일과 공유하는 내부 키일 뿐 — 실제 데이터는 센텔리안24 브랜드 전체다
# (검색어 centellian 24·センテリアン24 포함, BSR 은 PDRN 세럼·앰플 등 포함, 매출 = 브랜드 매출).
LABEL = {"madeca cream": "센텔리안24 (동국제약)", "reedle shot": "VT 리들샷 (브이티)",
         "medicube": "메디큐브 (에이피알)", "atopalm": "아토팜 (네오팜)", "cosrx": "코스알엑스",
         "anua": "아누아", "d'alba": "달바", "manyo": "마녀공장", "laneige": "라네즈 (아모레)",
         "skin1004": "SKIN1004", "beauty of joseon": "조선미녀", "tirtir": "티르티르",
         "torriden": "토리든", "numbuzin": "넘버즈인", "round lab": "라운드랩", "abib": "아비브",
         "mixsoon": "믹순", "biodance": "바이오던스"}

st.set_page_config(page_title="Amazon Tracker", page_icon="📦", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("beauty")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 6px 12px; margin: 0.9rem 0 0.5rem 0; }
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
div[data-baseweb="select"] > div { flex-wrap: wrap !important; height: auto !important; min-height: 38px; }
div[data-baseweb="select"] span[title] { max-width: none !important; text-overflow: clip !important; }
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
    return pd.read_csv(p, encoding="utf-8-sig")


def get(name):
    return load(name, _stamp(name))


def meta(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def lab(b):
    return LABEL.get(b, b)


# ------------------------------------------------------------------ 데이터
parts = []
for fn, geo in (("bsr_monthly.csv", "US"), ("bsr_monthly_jp.csv", "JP")):
    x = get(fn)
    if x is not None:
        x = x.copy()
        x["geo"] = geo
        parts.append(x)
if not parts:
    st.title("📦 Amazon Tracker")
    st.warning("BSR 데이터가 없습니다. `python keepa_bsr_history.py` 를 먼저 돌려주세요.")
    st.stop()
bm = pd.concat(parts, ignore_index=True)
bm["dt"] = pd.to_datetime(bm["month"] + "-01")
res = get("funnel_result.csv")
byb = get("funnel_by_brand.csv")
panel = get("funnel_panel.csv")
m_us, m_jp = meta("bsr_meta.json"), meta("bsr_meta_jp.json")
n_us = sum(v.get("points", 0) for v in (m_us.get("asins") or {}).values())
n_jp = sum(v.get("points", 0) for v in (m_jp.get("asins") or {}).values())

st.title("📦 Amazon Tracker — K뷰티 판매순위(BSR)")
st.caption(f"출처: Keepa API (Starter €49/월) · 미국 {len(m_us.get('asins') or {})}개 · "
           f"일본 {len(m_jp.get('asins') or {})}개 상품 · BSR 기록 {n_us + n_jp:,}개 · "
           f"갱신 {(m_jp.get('fetched') or m_us.get('fetched') or '')[:10]}")
st.markdown(
    "**BSR (Best Sellers Rank)** = 아마존 카테고리 안 판매 순위. **숫자가 작을수록 잘 팔림** "
    "(1위가 최고). 매출을 공개하지 않는 브랜드도 BSR 로 판매 흐름을 볼 수 있습니다.")

# 열자마자 기본 4개 브랜드 차트가 보이게 BSR 추이 탭을 맨 앞에 둔다 (PM 2026-10-15)
tab2, tab1, tab3 = st.tabs(["① 브랜드별 BSR 추이", "② 퍼널 검증 (검색 → BSR → 매출)", "③ 추적 상품 목록"])

# ================================================================ ① 퍼널 검증
with tab1:
    sub("결론", "18개 브랜드 · 분기 · 전년 대비 증감 · 순위상관(스피어만)")
    if res is None:
        st.info("`python funnel_study.py` 를 먼저 돌려주세요.")
    else:
        main = res[~res["단계"].str.contains("단일브랜드")].copy()
        order = ["① 상대검색 → 절대검색", "②a 절대검색 → BSR", "②b BSR → 매출",
                 "② 절대검색 → 매출", "③ 상대검색 → 매출 (전체 건너뛰기)"]
        best = (main.loc[main.groupby("단계")["R(순위)"].apply(lambda s: s.abs().idxmax())]
                .set_index("단계").reindex([o for o in order if o in set(main["단계"])])
                .reset_index())
        cols = st.columns(len(best))
        for c, (_, r) in zip(cols, best.iterrows()):
            ok = r["p값"] < 0.05
            c.metric(r["단계"].split(" (")[0], f"R = {r['R(순위)']:.2f}",
                     f"{int(r['시차(분기)'])}분기 뒤 · n={int(r['n'])} · "
                     + ("유의 ✅" if ok else "유의X"),
                     delta_color="normal" if ok else "off")
        # 최적 시차는 데이터에서 읽는다 — 고정 문장이 결과와 어긋나지 않게
        _lag = dict(zip(best["단계"], best["시차(분기)"].astype(int)))
        _l_ab = _lag.get("②a 절대검색 → BSR", 0)
        _l_br = _lag.get("②b BSR → 매출", 0)
        st.markdown(
            f"- **퍼널 순서가 맞습니다.** 검색이 오르면 BSR 이 약 {_l_ab}분기 뒤에 가장 크게 좋아지고, "
            f"BSR 과 매출은 {'같은 분기에' if _l_br == 0 else f'약 {_l_br}분기 차이로'} 가장 강하게 "
            "같이 움직입니다.\n"
            "- 모든 단계가 통계적으로 유의(p < 0.05)합니다. 표본은 브랜드-분기 단위입니다.\n"
            "- **R 은 0~1 사이의 '같이 움직이는 정도'** 입니다. 0.3 이면 약하지만 분명한 관계, "
            "0.5 이상이면 꽤 강한 관계입니다.")
        with st.expander("시차별 전체 표 보기"):
            show = main.copy()
            show["R(순위)"] = show["R(순위)"].round(3)
            show["R(피어슨)"] = show["R(피어슨)"].round(3)
            show["p값"] = show["p값"].map(lambda v: "<0.001" if v < 0.001 else f"{v:.3f}")
            st.dataframe(show, hide_index=True, use_container_width=True)

    sub("브랜드별 결과", "브랜드 하나만 보면 점이 10~30개라 흔들림 — 전체 결론이 더 믿을 만함")
    if byb is not None:
        t = byb.copy()
        t["브랜드"] = t["brand"].map(lab)
        keep = {"②a절대→BSR": "검색→BSR", "②bBSR→매출": "BSR→매출", "②절대→매출": "검색→매출"}
        out = t[["브랜드", "매출주기", "매출관측수"]].copy()
        for k, nm in keep.items():
            if f"{k}_R" in t:
                out[f"{nm} R"] = t[f"{k}_R"].round(2)
                out[f"{nm} n"] = t[f"{k}_n"].fillna(0).astype(int)
                out[f"{nm} 판정"] = np.where(
                    t[f"{k}_n"].fillna(0) < 6, "표본부족",
                    np.where(t[f"{k}_p"] < 0.05, np.where(t[f"{k}_R"] > 0, "✅ 양(+)", "⚠️ 음(−)"),
                             "유의X"))
        out = out.sort_values("검색→BSR R", ascending=False, na_position="last")
        st.dataframe(out, hide_index=True, use_container_width=True, height=560)
        st.caption("✅ 양(+) = 같이 오름 (퍼널대로) · ⚠️ 음(−) = 반대로 움직임 · "
                   "표본부족 = 겹치는 분기가 6개 미만 · 매출 단위 KRWmn")

    sub("주의할 점")
    st.markdown(
        "1. **BSR 은 카테고리 안 순위**입니다. 카테고리가 다른 상품끼리 순위 숫자를 직접 비교하면 안 됩니다. "
        "그래서 브랜드 안에서 '작년보다 좋아졌나'만 봅니다.\n"
        "2. **미국·일본 BSR 은 브랜드별 검색 비중으로 가중평균**했습니다. 리들샷은 검색의 90%가 일본이라 "
        "일본 BSR 이 거의 전부를 결정합니다.\n"
        "3. **BSR 이 좋아져도 매출이 안 따라오는 브랜드가 있습니다** — "
        + (", ".join(f"{lab(r['brand'])} {r['②bBSR→매출_R']:+.2f}" for _, r in byb.iterrows()
                     if pd.notna(r.get("②bBSR→매출_R")) and r["②bBSR→매출_R"] < 0
                     and r["②bBSR→매출_p"] < 0.05) if byb is not None else "")
        + ". 매출이 꺾였거나 정체된 구간이거나, 매출이 회사 전체 숫자인 경우입니다. 아마존 순위만으로 "
        "매출을 단정하면 안 됩니다.\n"
        "4. 매출은 **회사 단위**인 곳이 있습니다 (리들샷 = VT 연결 전사, 라네즈 = 아모레 전사). "
        "브랜드 신호가 희석됩니다.")

# ================================================================ ② 브랜드별 추이
with tab2:
    sub("브랜드별 BSR 추이", "월별 중앙값 · 위로 갈수록 잘 팔림 (축을 뒤집음)")
    brands = sorted(bm["brand"].unique(), key=lambda b: (b not in FOCUS, FOCUS.index(b) if b in FOCUS else 0, b))
    c1, c2, c3 = st.columns([2.6, 1.2, 1.6])
    with c1:
        sel = st.multiselect("브랜드", brands, default=[b for b in DEFAULT if b in brands],
                             format_func=lab, key="az_brand")
    with c2:
        mk = st.radio("마켓", ["미국", "일본"], horizontal=True, key="az_mkt")
    with c3:
        span = st.radio("구간", ["1년", "2년", "3년", "5년", "전체"], index=2, horizontal=True, key="az_span")
    geo = "US" if mk == "미국" else "JP"
    d = bm[(bm["geo"] == geo) & (bm["brand"].isin(sel))].copy()
    if span != "전체" and len(d):
        yrs = int(span[0])
        d = d[d["dt"] >= d["dt"].max() - pd.DateOffset(years=yrs)]
    if not sel:
        st.info("브랜드를 하나 이상 고르세요.")
    elif d.empty:
        st.info(f"{mk} 아마존에 고른 브랜드의 BSR 기록이 없습니다.")
    else:
        d["브랜드"] = d["brand"].map(lab)
        ch = alt.Chart(d).mark_line(point=alt.OverlayMarkDef(size=18)).encode(
            x=alt.X("dt:T", title=None, axis=alt.Axis(format="%Y-%m", labelAngle=0, tickCount=12)),
            y=alt.Y("bsr_median:Q", title="BSR (월 중앙값, 로그 · 위 = 잘 팔림)",
                    scale=alt.Scale(type="log", reverse=True)),
            color=alt.Color("브랜드:N", legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("브랜드:N"), alt.Tooltip("month:N", title="월"),
                     alt.Tooltip("bsr_median:Q", format=",.0f", title="BSR 중앙값"),
                     alt.Tooltip("n_asin:Q", title="상품 수")])
        st.altair_chart(ch.properties(height=430), use_container_width=True)
        st.caption("BSR 은 하루에도 여러 번 바뀌어 튀는 값이 많습니다. 그래서 상품별 월 중앙값 → 브랜드 "
                   "중앙값으로 묶었습니다. 세로축은 로그·뒤집힘이라 선이 올라가면 순위가 좋아진 것입니다.")

    sub("한 브랜드 퍼널 — 검색 · BSR · 매출을 한 화면에", "분기 · 각 선을 자기 최저=0, 최고=100 으로 맞춤")
    if panel is not None:
        _opts = [b for b in brands if b in set(panel["brand"])]
        pb = st.selectbox("브랜드", _opts, format_func=lab, key="az_one",
                          index=_opts.index("madeca cream") if "madeca cream" in _opts else 0)
        g = panel[panel["brand"] == pb].sort_values("q").copy()
        g = g[g["q"] >= "2019Q1"]
        lines = []
        for col, nm in (("abs_search", "절대검색 (전세계)"), ("bsr", "BSR 강도 (미·일)"),
                        ("rev", "매출 (KRWmn)")):
            if col in g and g[col].notna().sum() >= 2:
                s = g[["q", col]].dropna().copy()
                lo, hi = s[col].min(), s[col].max()
                s["지수"] = 100 * (s[col] - lo) / (hi - lo) if hi > lo else 50.0
                s["원값"] = s[col]
                s["지표"] = nm
                lines.append(s[["q", "지수", "원값", "지표"]])
        if lines:
            L = pd.concat(lines)
            L["dt"] = pd.PeriodIndex(L["q"], freq="Q").to_timestamp(how="end").normalize()
            colors = alt.Scale(domain=["절대검색 (전세계)", "BSR 강도 (미·일)", "매출 (KRWmn)"],
                               range=[C_SEARCH, C_BSR, C_REV])
            base = alt.Chart(L).encode(
                x=alt.X("dt:T", title=None, axis=alt.Axis(format="%Y", tickCount="year", labelAngle=0)),
                y=alt.Y("지수:Q", title="지수 (자기 최저 0 ~ 최고 100)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("지표:N", scale=colors, legend=alt.Legend(orient="top", title=None)),
                tooltip=[alt.Tooltip("지표:N"), alt.Tooltip("q:N", title="분기"),
                         alt.Tooltip("원값:Q", format=",.2f"), alt.Tooltip("지수:Q", format=".0f")])
            st.altair_chart((base.mark_line(strokeWidth=2.5) + base.mark_point(size=30, filled=True))
                            .properties(height=380), use_container_width=True)
            st.caption("세 지표의 단위가 달라(검색 횟수 · 순위 · KRWmn) 각자 최저=0, 최고=100 으로 맞췄습니다. "
                       "모양(언제 오르고 내리는지)만 비교하세요. 매출이 연간뿐인 브랜드는 매년 4분기에 한 점만 "
                       "있습니다. BSR 강도 = −log10(BSR), 클수록 잘 팔림.")
            if byb is not None and pb in set(byb["brand"]):
                rr = byb[byb["brand"] == pb].iloc[0]

                def _fmt(k):
                    if pd.isna(rr.get(f"{k}_R")):
                        return f"표본부족 (n={int(rr.get(f'{k}_n') or 0)})"
                    return (f"R {rr[f'{k}_R']:+.2f} · p {rr[f'{k}_p']:.2f} · "
                            f"{int(rr[f'{k}_시차'])}분기 뒤 · n={int(rr[f'{k}_n'])}")
                st.markdown(f"**{lab(pb)}** — 검색→BSR: {_fmt('②a절대→BSR')}  \n"
                            f"BSR→매출: {_fmt('②bBSR→매출')}  \n검색→매출: {_fmt('②절대→매출')}")

# ================================================================ ③ 상품 목록
with tab3:
    sub("추적 중인 상품 (ASIN)", "ASIN = 아마존 상품 고유번호 · 브랜드별 판매순위 상위 상품")
    rows = []
    for fn, mf, geo in (("bsr_asins.csv", m_us, "US"), ("bsr_asins_jp.csv", m_jp, "JP")):
        a = get(fn)
        if a is None:
            continue
        info = mf.get("asins") or {}
        for _, r in a.iterrows():
            i = info.get(r["asin"], {})
            rows.append({"마켓": MKT[geo], "브랜드": lab(r["brand"]), "ASIN": r["asin"],
                         "상품명": (i.get("title") or r.get("title") or "")[:80],
                         "BSR 기록 수": i.get("points", 0)})
    if rows:
        tl = pd.DataFrame(rows)
        f1, f2 = st.columns([1, 3])
        with f1:
            mf_ = st.radio("마켓", ["전체"] + list(MKT.values()), key="az_tbl")
        if mf_ != "전체":
            tl = tl[tl["마켓"] == mf_]
        with f2:
            st.caption(f"{len(tl)}개 상품. 브랜드명 검색이 엉뚱한 상품을 물어온 적이 있어(VT → USB 헤드셋, "
                       "달바 → 슬라임·주방용품, 마녀공장 → 이쑤시개) 제품명으로 다시 찾았고, 지금은 상품명에 "
                       "브랜드명이 없으면 자동으로 버립니다. 센텔리안24 는 마데카크림 외 PDRN 세럼·앰플·"
                       "캡슐세럼도 포함합니다.")
        st.dataframe(tl, hide_index=True, use_container_width=True, height=620,
                     column_config={"BSR 기록 수": st.column_config.NumberColumn(format="%d")})
