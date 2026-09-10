# -*- coding: utf-8 -*-
"""Cosmetics / Beauty 섹터 — 동국제약 센텔리안24 미국 수요 트래커.

- 구글 트렌드(미국): 자동 일일 수집 (cosmetics_update.py, 일배치 포함)
- 아마존: 약관상 자동 수집 금지(kbeauty/docs/ACCESS_REVIEW.md) →
  수동 스냅샷(manual_amazon.csv) + Keepa API 구독 시 자동화 가능
"""
import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"

st.set_page_config(page_title="Cosmetics/Beauty", page_icon="💄", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("beauty")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 1.18rem; font-weight: 600; background: #2a4a73;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 7px 14px; margin: 0.9rem 0 0.5rem 0;
}
.lk-h span { font-weight: 300; font-size: 0.85rem; opacity: 0.8; margin-left: 8px; }
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
            x=alt.X("date:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
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
            x=alt.X("date:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
            y=alt.Y("value:Q", title="검색 관심도 (상대값)"),
            color=alt.Color("keyword:N", title=None,
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("date:T"), "value"])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        st.caption("**읽는법**: anua·medicube·cosrx 같은 대형 K뷰티 브랜드 대비 "
                   "**madeca cream**(센텔리안24의 히어로 제품명 — 미국 소비자가 "
                   "실제로 검색하는 단어)의 위치. 격차가 좁혀지는지가 아마존 채널 "
                   "성장 여력의 가늠자.")


# --------------------------------------------- 트렌드 파생 지표 (YoY·Mindshare)
def _monthly(df):
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.to_period("M")
    m = d.groupby(["month", "keyword"], as_index=False)["value"].mean()
    return m.sort_values("month")


def _mindshare(df):
    m = _monthly(df)
    tot = m.groupby("month")["value"].transform("sum")
    m["share"] = (m["value"] / tot * 100).where(tot > 0)
    m["month"] = m["month"].dt.to_timestamp()
    return m


def _yoy(df):
    m = _monthly(df)
    m["base"] = m.groupby("keyword")["value"].shift(12)
    # 1년 전 값이 너무 작으면(관심도 5 미만) YoY %가 수천%로 튀어 의미가 없다
    m["yoy"] = ((m["value"] / m["base"] - 1) * 100).where(m["base"] >= 5)
    m["month"] = m["month"].dt.to_timestamp()
    return m.dropna(subset=["yoy"])


g3, g4 = st.columns(2, gap="large")
with g3:
    sub("검색량 YoY 증가율", "구글 트렌드 5년치 · 월 평균 · 전년 같은 달 대비 %")
    s5 = load("gtrends_solo_5y.csv", _stamp("gtrends_solo_5y.csv"))
    if s5 is not None and len(s5):
        yy = _yoy(s5)
        yy = yy[yy["month"] >= yy["month"].max() - pd.DateOffset(months=36)]
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            color=C_GOLD, strokeDash=[4, 3]).encode(y="y:Q")
        ch = alt.Chart(yy).mark_line(size=2.5, point=True).encode(
            x=alt.X("month:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
            y=alt.Y("yoy:Q", title="YoY (%)"),
            color=alt.Color("keyword:N", title=None,
                            scale=alt.Scale(domain=["madeca cream", "centellian24"],
                                            range=[C_LINE, C_BAR]),
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("month:T"),
                     alt.Tooltip("yoy:Q", format="+.0f")])
        st.altair_chart((ch + zero).properties(height=280),
                        use_container_width=True)
        st.caption("**읽는법**: 작년 같은 달보다 검색이 얼마나 늘었는지(%). 금색 "
                   "점선(0%) 위 = 성장. 계절성(연말 선물 시즌 등)을 걷어낸 실제 "
                   "성장 속도. 1년 전 관심도가 5 미만인 달은 %가 수천%로 튀어 "
                   "제외. 마지막 달은 진행 중이라 값이 바뀔 수 있음.")
    else:
        st.info("5년치 데이터가 아직 없습니다 — 다음 일배치에서 생성됩니다.")
with g4:
    sub("Mindshare — K뷰티 브랜드 검색 점유율", "같은 묶음 상대값 ÷ 합계 · 월 평균")
    if comp is not None and len(comp):
        ms = _mindshare(comp)
        cur_m = ms[ms["month"] == ms["month"].max()].set_index("keyword")["share"]
        prv_m = ms[ms["month"] == sorted(ms["month"].unique())[-2]] \
            .set_index("keyword")["share"] if ms["month"].nunique() >= 2 else cur_m
        ch = alt.Chart(ms).mark_area().encode(
            x=alt.X("month:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
            y=alt.Y("share:Q", stack=True, title="Mindshare (%)",
                    scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("keyword:N", title=None,
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("month:T"),
                     alt.Tooltip("share:Q", format=".1f")])
        st.altair_chart(ch.properties(height=280), use_container_width=True)
        parts = [f"{k} {cur_m[k]:.1f}% ({cur_m[k] - prv_m.get(k, cur_m[k]):+.1f}%p)"
                 for k in cur_m.sort_values(ascending=False).index]
        st.caption("**최신 월 점유율**: " + " · ".join(parts)
                   + " — 검색량 기준 상대 점유(절대 판매량 아님). 센텔리안 몫이 "
                     "커지는지가 관전 포인트.")

# --------------------------------------------- 브랜드 수명주기 (t=0 정렬)
_LGEO = {"미국": "US", "일본": "JP", "한국": "KR", "영국": "GB", "전세계": ""}
_avail = {k: v for k, v in _LGEO.items()
          if (DATA / f"gtrends_life_{v}.csv").exists()}
if _avail:
    sub("K뷰티 브랜드 수명주기 — 붐 시작(t=0) 정렬",
        "브랜드별 단독 5년 검색 · 자기 피크=100 · x축 = 붐 시작 후 개월 수")
    lc1, lc2 = st.columns([1, 3.2])
    geo_l = lc1.selectbox("국가", list(_avail), key="life_geo")
    lf = load(f"gtrends_life_{_avail[geo_l]}.csv",
              _stamp(f"gtrends_life_{_avail[geo_l]}.csv"))
    if lf is not None and len(lf):
        d = lf.copy()
        d["date"] = pd.to_datetime(d["date"])
        d["month"] = d["date"].dt.to_period("M")
        mm = d.groupby(["brand", "month"], as_index=False)["value"].mean()
        rows = []
        for b, g in mm.groupby("brand"):
            g = g.sort_values("month").copy()
            peak = g["value"].max()
            if peak <= 0:
                continue
            g["norm"] = g["value"] / peak * 100
            br = g[g["norm"] >= 10]                 # 붐 시작 = 자기 피크의 10%
            if not len(br):
                continue
            b0 = br["month"].iloc[0]
            g = g[g["month"] >= b0]
            g["m_since"] = [(p.year - b0.year) * 12 + (p.month - b0.month)
                            for p in g["month"]]
            g["breakout"] = b0.strftime("%Y-%m")
            rows.append(g)
        if rows:
            life = pd.concat(rows)
            _all = sorted(life["brand"].unique())
            _def = [b for b in ("madeca cream", "reedle shot", "medicube",
                                "anua", "cosrx", "tirtir", "beauty of joseon")
                    if b in _all]
            sel = lc2.multiselect("브랜드 (추가/제거 가능)", _all, default=_def,
                                  key="life_sel")
            v = life[life["brand"].isin(sel)].copy()
            if len(v):
                _bsel = sorted(v["brand"].unique())
                _pal2 = ["#2a78d6", "#8ec9ff", "#4fb8c9", "#eb6834", "#b06fc9",
                         "#4fb862", "#e8425a", "#b5b5b5", "#2fa89a", "#d98cb3",
                         "#7a8ff0", "#c9a34f", "#5f7089", "#9fd65f", "#ef9f4f",
                         "#66d0e0", "#ff7ab0"]
                _cols = []
                _pi = 0
                for b in _bsel:
                    if b == "madeca cream":
                        _cols.append(C_GOLD)
                    else:
                        _cols.append(_pal2[_pi % len(_pal2)])
                        _pi += 1
                ch = alt.Chart(v).mark_line(interpolate="monotone").encode(
                    x=alt.X("m_since:Q",
                            title="붐 시작 후 개월 (t=0 = 자기 피크의 10% 첫 도달)"),
                    y=alt.Y("norm:Q", title="검색 관심도 (자기 피크=100)"),
                    color=alt.Color("brand:N", title=None,
                                    scale=alt.Scale(domain=_bsel, range=_cols),
                                    legend=alt.Legend(orient="top", columns=6,
                                                      labelLimit=160)),
                    size=alt.condition(alt.datum.brand == "madeca cream",
                                       alt.value(4.5), alt.value(1.7)),
                    tooltip=["brand", "breakout",
                             alt.Tooltip("m_since:Q", title="개월"),
                             alt.Tooltip("norm:Q", format=".0f")])
                st.altair_chart(ch.properties(height=430),
                                use_container_width=True)
                ages = (v.groupby("brand")
                        .agg(b0=("breakout", "first"), age=("m_since", "max"))
                        .sort_values("age"))
                parts = [f"{b}: {r['b0']} 시작·{r['age']:.0f}개월차"
                         for b, r in ages.iterrows()]
                st.caption("**붐 시작 시점**: " + " · ".join(parts))
                _jp_note = (" 일본 주의: 구글+야후재팬(구글 엔진)이 검색의 약 "
                            "90%라 방향은 유효하지만, 일본 소비자는 @cosme·"
                            "Qoo10·LIPS 앱에서 화장품을 찾는 비중이 커서 보조 "
                            "지표로 쓸 것. 검색어는 가타카나 매핑 사용."
                            if geo_l == "일본" else "")
                st.caption("**읽는법**: 모든 브랜드를 각자의 붐 시작 시점(t=0)에 "
                           "맞춰 겹친 차트 — 굵은 금색 = madeca cream. 같은 "
                           "개월수에서 벤치마크 곡선이 앞으로 어떻게 갔는지가 "
                           "madeca의 시나리오. 각 선은 자기 피크=100의 상대값이라 "
                           "**모양(단계) 비교용**이며 브랜드끼리 크기 비교는 아님."
                           + _jp_note)
    else:
        st.info("수명주기 데이터 수집 중 — cosmetics_lifecycle_update.py 실행 후 "
                "표시됩니다.")

# --------------------------------------------- 구글 트렌드 직접 검색
sub("구글 트렌드 직접 검색", "원하는 브랜드 최대 5개 — 관심도·Mindshare·YoY 한 번에")
_GEO = {"미국": "US", "전세계": "", "한국": "KR"}
_TF = {"3개월": "today 3-m", "12개월": "today 12-m", "5년": "today 5-y",
       "전체 (2004~)": "all"}
_CAT = {"뷰티·피트니스": 44, "전체": 0}
c1, c2, c3, c4, c5 = st.columns([2.8, 0.9, 0.9, 1.1, 0.8])
kw_in = c1.text_input("키워드 (쉼표로 구분, 최대 5개)",
                      value="madeca cream, medicube, anua, cosrx, biodance",
                      key="gt_kw")
geo_k = c2.selectbox("지역", list(_GEO), key="gt_geo")
tf_k = c3.selectbox("기간", list(_TF), index=2, key="gt_tf")
cat_k = c4.selectbox("카테고리", list(_CAT), key="gt_cat",
                     help="뷰티·피트니스로 좁히면 뷰티 외 바이럴 검색이 빠져 "
                          "실수요에 더 가까움 — 구글 화면과 동일 조건")
c5.write("")
go = c5.button("조회", type="primary", use_container_width=True)


@st.cache_data(ttl=3600, show_spinner="구글 트렌드 조회 중… (10초 정도)")
def _gt_fetch(kws, geo, tf, cat):
    from gtrends import fetch_trends
    return fetch_trends(list(kws), geo=geo, timeframe=tf, category=cat)


if go:
    kws = [k.strip() for k in kw_in.split(",") if k.strip()][:5]
    if not kws:
        st.warning("키워드를 1개 이상 넣어주세요.")
    else:
        try:
            st.session_state["gt_res"] = {
                "df": _gt_fetch(tuple(kws), _GEO[geo_k], _TF[tf_k],
                                _CAT[cat_k]),
                "kws": kws, "geo": geo_k, "tf": tf_k}
        except Exception:
            st.error("구글이 요청을 막았습니다 (429 요청 과다일 가능성). 1~2분 뒤 "
                     "다시 눌러보세요. 클라우드 서버에서는 차단이 잦습니다 — "
                     "계속 안 되면 로컬에서 확인해 드립니다.")

_res = st.session_state.get("gt_res")
if _res:
    rdf, rk = _res["df"], _res["kws"]
    st.caption(f"조회: {', '.join(rk)} · {_res['geo']} · {_res['tf']} — "
               "값은 이 묶음 안에서의 상대값(최고=100)")
    def _raw_chart(height):
        d = rdf.copy()
        d["date"] = pd.to_datetime(d["date"])
        ch = alt.Chart(d).mark_line(size=2).encode(
            x=alt.X("date:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
            y=alt.Y("value:Q", title="검색 관심도 (상대값)"),
            color=alt.Color("keyword:N", title=None,
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("date:T"), "value"])
        st.altair_chart(ch.properties(height=height), use_container_width=True)

    if len(rk) >= 2:
        ms = _mindshare(rdf)
        cur_m = ms[ms["month"] == ms["month"].max()].set_index("keyword")["share"]
        prv_m = ms[ms["month"] == sorted(ms["month"].unique())[-2]] \
            .set_index("keyword")["share"] if ms["month"].nunique() >= 2 else cur_m
        mcols = st.columns(len(rk))
        for col, k in zip(mcols, cur_m.sort_values(ascending=False).index):
            col.metric(k, f"{cur_m[k]:.1f}%",
                       f"{cur_m[k] - prv_m.get(k, cur_m[k]):+.1f}%p vs 직전 월")
        r1, r2 = st.columns(2, gap="large")
        with r1:
            _raw_chart(270)
            st.caption("원본 관심도 — 같은 묶음 안 상대 비교")
        with r2:
            ch = alt.Chart(ms).mark_area().encode(
                x=alt.X("month:T", title=None,
                        axis=alt.Axis(format="%y %b", labelAngle=0)),
                y=alt.Y("share:Q", stack=True, title="Mindshare (%)",
                        scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("keyword:N", title=None,
                                legend=alt.Legend(orient="top")),
                tooltip=["keyword", alt.Tooltip("month:T"),
                         alt.Tooltip("share:Q", format=".1f")])
            st.altair_chart(ch.properties(height=270), use_container_width=True)
            st.caption("Mindshare — 월 평균 관심도 ÷ 묶음 합계")
    else:
        _raw_chart(320)
        st.caption("원본 관심도 — 이 키워드 자체 기준(최고=100). Mindshare는 "
                   "비교 키워드를 쉼표로 추가하면 나타납니다.")
    if _res["tf"] in ("5년", "전체 (2004~)"):
        yy = _yoy(rdf)
        yy = yy[yy["month"] >= yy["month"].max() - pd.DateOffset(months=36)]
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            color=C_GOLD, strokeDash=[4, 3]).encode(y="y:Q")
        ch = alt.Chart(yy).mark_line(size=2, point=True).encode(
            x=alt.X("month:T", title=None,
                    axis=alt.Axis(format="%y %b", labelAngle=0)),
            y=alt.Y("yoy:Q", title="YoY (%)"),
            color=alt.Color("keyword:N", title=None,
                            legend=alt.Legend(orient="top")),
            tooltip=["keyword", alt.Tooltip("month:T"),
                     alt.Tooltip("yoy:Q", format="+.0f")])
        st.altair_chart((ch + zero).properties(height=270),
                        use_container_width=True)
        st.caption("YoY 증가율 — 전년 같은 달 대비 %. 0% 금색 점선 위 = 성장.")
    else:
        st.caption("YoY 증가율을 보려면 기간을 '5년'으로 선택하세요.")

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
    # 숫자는 숫자 그대로 둬야 열 클릭 정렬이 크기순으로 됨 (문자로 바꾸면
    # "100,000"이 "20,000"보다 앞에 오는 사전순 정렬이 됨). Styler 행 하이라이트는
    # 빈 값을 'None'으로 찍는 버그가 있어 안 씀 — 센텔리안은 🟡 마커로 표시.
    for c in ("Δ", "세부 카테고리", "비고"):
        view[c] = view[c].fillna("—")
    for c in ("순위", "가격(원)", "정가(원)", "할인%", "평점", "리뷰 수",
              "월 구매(개+)", "BSR 뷰티", "세부 순위"):
        view[c] = view[c].astype("Float64")
    view.loc[show["brand"].eq("CENTELLIAN 24").values, "브랜드"] = \
        "🟡 CENTELLIAN 24"
    _num = st.column_config.NumberColumn
    st.dataframe(
        view, hide_index=True, use_container_width=True,
        height=min(430, 40 + 35 * len(view)),
        column_config={
            "순위": _num(format="%d"),
            "가격(원)": _num(format="localized"),
            "정가(원)": _num(format="localized"),
            "할인%": _num(format="%.0f%%"),
            "평점": _num(format="%.1f"),
            "리뷰 수": _num(format="localized"),
            "월 구매(개+)": _num(format="localized"),
            "BSR 뷰티": _num(format="%d"),
            "세부 순위": _num(format="%d"),
        })
    st.caption("**읽는법**: 순위=아마존 '페이셜 크림·모이스처라이저' 베스트셀러(판매 "
               "속도 기준, 자주 갱신), Δ=직전 스냅샷 대비 이동. '월 구매'는 아마존 "
               "표시값(1천+, 5만+ 식 반올림). 열 제목을 클릭하면 크기순 정렬. "
               "회색 'None' = 데이터 없음 — 배송지가 한국이라 일부 리스팅은 "
               "가격·월구매를 숨김(비고 참조). 'Customers say' AI 요약은 로그인 "
               "화면에만 표시돼 아직 미수집. 실리콘투(257720) 프록시로 쓸 때는 "
               "브랜드별 유통 경로(직판 vs 수출대행)를 따로 확인할 것.")

    # ------------------------------------------- 월 구매 추이 (날짜별 세로 막대)
    sub("아마존 월 구매 추이 — 판매량 트래킹",
        "각 막대 = 관측일 기준 직전 30일 구매 (달력상 '8월' 같은 월별 수치 아님)")
    hist = aw[(aw["kbeauty"] == 1) & aw["bought_month"].notna()][
        ["date", "brand", "product", "bought_month"]].copy()
    # 워치 시작(9/9) 전의 수동 스냅샷에서 센텔리안 히어로 기록을 이어 붙인다
    if am is not None and len(am):
        _h = am[am["product"].astype(str).str.contains("타임 리버스 50ml", na=False)
                & am["bought_last_month"].notna()]
        for _, r in _h.iterrows():
            hist.loc[len(hist)] = [r["date"], "CENTELLIAN 24",
                                   "Madeca 크림 타임 리버스 50ml",
                                   r["bought_last_month"]]
    if len(hist):
        hist["label"] = hist["brand"] + " " + hist["product"].str.slice(0, 12)
        hist = (hist.groupby(["date", "label"], as_index=False)["bought_month"]
                .max())
        labs = sorted(hist["label"].unique())
        pal = ["#2a78d6", "#8ec9ff", "#4fb8c9", "#eb6834", "#b06fc9", "#4fb862",
               "#b5b5b5"]
        colors = [C_GOLD if l.startswith("CENTELLIAN") else pal[i % len(pal)]
                  for i, l in enumerate(labs)]
        cscale = alt.Scale(domain=labs, range=colors)
        cleg = alt.Legend(orient="top", labelLimit=260, columns=3)
        hist["date_dt"] = pd.to_datetime(hist["date"])
        _ws = hist["date_dt"] - pd.to_timedelta(hist["date_dt"].dt.weekday,
                                                unit="D")
        hist["week"] = (_ws.dt.strftime("%Y.%m.%d") + "~"
                        + (_ws + pd.Timedelta(days=6)).dt.strftime("%m.%d"))
        # 시간축 도메인: 데이터는 왼쪽 끝부터, 오른쪽은 앞으로 채워질 날짜 공간
        def _tdom(s):
            return [s.min().isoformat(),
                    (s.max() + pd.Timedelta(days=12)).isoformat()]

        _dom = _tdom(hist["date_dt"])

        # ① 주간 트래킹 — 한 주에 스냅샷이 여러 번이면 마지막 값
        sub("① 주간 트래킹 — 주 단위로 쌓이는 기록",
            "x축 = 관측 주간 (월~일) · 값 = 그 주 마지막 스냅샷의 직전 30일 구매")
        wk = (hist.sort_values("date_dt")
              .groupby(["week", "label"], as_index=False).last())
        base_w = alt.Chart(wk).encode(
            x=alt.X("week:O", title="관측 주간", sort=None,
                    axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("label:N"),
            y=alt.Y("bought_month:Q", title="직전 30일 구매 (개+, 표시값)"),
            color=alt.Color("label:N", title=None, scale=cscale, legend=cleg))
        bars_w = base_w.mark_bar(width={"band": 0.9})
        txt_w = base_w.mark_text(dy=-8, fontSize=11, color="#c6d0de").encode(
            text=alt.Text("bought_month:Q", format=",.0f"))
        st.altair_chart((bars_w + txt_w).properties(height=430),
                        use_container_width=True)
        st.caption("**읽는법**: 주 1회 스냅샷이 쌓이면 이 차트가 주간 추세가 됨. "
                   "아마존은 주간 판매량 자체는 공개하지 않으므로, 값은 그 주에 "
                   "본 '직전 30일 구매' — **주와 주 사이에 구간이 바뀌는 것** "
                   "(5만+→6만+)이 신호. 센텔리안 = 금색.")

        # ② 롤링 30일 원본 — 관측일별 전 기록
        sub("② 롤링 30일 추이 — 관측일별 원본 기록",
            "각 점 = 그날 본 '지난달(직전 30일) 구매' · 선이 위로 꺾이면 가속")
        base_r = alt.Chart(hist).encode(
            x=alt.X("date_dt:T", title="관측일 (이날 기준 직전 30일)",
                    scale=alt.Scale(domain=_dom),
                    axis=alt.Axis(format="%m/%d", tickCount="day",
                                  labelAngle=0)),
            y=alt.Y("bought_month:Q", title="직전 30일 구매 (개+, 표시값)"),
            color=alt.Color("label:N", title=None, scale=cscale, legend=cleg))
        line_r = base_r.mark_line(size=2.5, point=alt.OverlayMarkDef(size=70),
                                  interpolate="monotone")
        txt_r = base_r.mark_text(dy=-12, fontSize=11, color="#c6d0de").encode(
            text=alt.Text("bought_month:Q", format=",.0f"))
        st.altair_chart((line_r + txt_r).properties(height=430),
                        use_container_width=True)
        st.caption("**읽는법**: '지난달 구매'는 달력상 월(8월 등)이 아니라 **보는 "
                   "시점부터 거꾸로 30일**을 센 롤링 값 — 9/9 점은 대략 8/10~9/9 "
                   "판매분. 주간 스냅샷끼리는 30일 중 23일이 겹쳐 값이 비슷하게 "
                   "나오는 게 정상 — 계단식으로 **구간이 바뀌는 순간**이 진짜 신호 "
                   "(반올림 표시값). 스냅샷이 쌓일수록 선이 촘촘해짐.")

        def _kscale(ls):
            ls = sorted(ls)
            cs = [C_GOLD if l.startswith("CENTELLIAN") else pal[i % len(pal)]
                  for i, l in enumerate(ls)]
            return alt.Scale(domain=ls, range=cs)

        # ③ 주간 판매 추정 — 리뷰 증분 방식 (반올림 없는 유일한 주간 지표)
        sub("③ 주간 판매 추정 — 리뷰 증가분 방식 (내 추정)",
            "주간 Δ리뷰 ÷ 리뷰 작성률 · 작성률 = (일평균 Δ리뷰 × 30) ÷ 최신 월구매")
        rv = aw[(aw["kbeauty"] == 1) & aw["reviews"].notna()][
            ["date", "brand", "product", "reviews"]].copy()
        if am is not None and len(am):
            _h = am[am["product"].astype(str).str.contains("타임 리버스 50ml",
                                                           na=False)
                    & am["reviews"].notna()]
            for _, r in _h.iterrows():
                rv.loc[len(rv)] = [r["date"], "CENTELLIAN 24",
                                   "Madeca 크림 타임 리버스 50ml", r["reviews"]]
        rv["label"] = rv["brand"] + " " + rv["product"].str.slice(0, 12)
        rv = rv.groupby(["date", "label"], as_index=False)["reviews"].max()
        rv["date_dt"] = pd.to_datetime(rv["date"])
        rv = rv.sort_values("date_dt")
        est_rows, ex = [], None
        for lab, g in rv.groupby("label"):
            if len(g) < 2:
                continue
            days_all = (g["date_dt"].iloc[-1] - g["date_dt"].iloc[0]).days
            drev_all = g["reviews"].iloc[-1] - g["reviews"].iloc[0]
            b = hist[hist["label"] == lab]
            if days_all <= 0 or drev_all <= 0 or not len(b):
                continue
            bought = b.sort_values("date_dt")["bought_month"].iloc[-1]
            rate = (drev_all / days_all * 30) / bought   # 구매 중 리뷰 작성 비율
            if not (0.001 <= rate <= 0.2):
                continue
            if lab.startswith("CENTELLIAN"):
                ex = (drev_all / days_all, rate)
            for i in range(1, len(g)):
                dd = (g["date_dt"].iloc[i] - g["date_dt"].iloc[i - 1]).days
                dr = g["reviews"].iloc[i] - g["reviews"].iloc[i - 1]
                if dd <= 0:
                    continue
                est_rows.append({"label": lab, "date": g["date_dt"].iloc[i],
                                 "weekly_est": dr / dd * 7 / rate})
        if est_rows:
            ed = pd.DataFrame(est_rows)
            base_e = alt.Chart(ed).encode(
                x=alt.X("date:T", title="스냅샷 일자",
                        scale=alt.Scale(domain=_tdom(ed["date"])),
                        axis=alt.Axis(format="%m/%d", tickCount="day",
                                      labelAngle=0)),
                y=alt.Y("weekly_est:Q", title="주간 판매 추정 (개)"),
                color=alt.Color("label:N", title=None,
                                scale=_kscale(ed["label"].unique()),
                                legend=cleg))
            ln_e = base_e.mark_line(size=2.5, point=alt.OverlayMarkDef(size=70))
            tx_e = base_e.mark_text(dy=-12, fontSize=11, color="#c6d0de").encode(
                text=alt.Text("weekly_est:Q", format=",.0f"))
            st.altair_chart((ln_e + tx_e).properties(height=380),
                            use_container_width=True)
            _exs = (f"지금 센텔리안: 리뷰 +{ex[0]:.0f}개/일 → 주간 "
                    f"+{ex[0] * 7:.0f}개 ÷ 작성률 {ex[1] * 100:.1f}% ≈ "
                    f"{ex[0] * 7 / ex[1]:,.0f}개/주. " if ex else "")
            st.caption("**읽는법**: 리뷰 수는 반올림 없는 정확한 누적치 — 주간 "
                       "Δ리뷰가 유일한 '진짜 주간 흐름'. 작성률(구매 몇 건당 리뷰 "
                       f"1개)은 월구매 표시값으로 보정한 **내 추정**. {_exs}"
                       "작성률은 프로모션 시기에 변할 수 있어 매달 재보정.")
        else:
            st.caption("리뷰 스냅샷이 2개 이상 쌓이면 여기에 주간 추정 판매가 "
                       "그려집니다 — 다음 '아마존 스냅샷 갱신' 때부터.")

        # ④ BSR 추이 — 시간당 갱신되는 가장 빠른 신호
        sub("④ BSR 추이 — 아마존 판매 속도 순위",
            "뷰티 전체 순위 · 선이 높을수록 빨리 팔림 (순위 숫자는 낮을수록 좋음 "
            "— 축 뒤집음)")
        bs = aw[(aw["kbeauty"] == 1) & aw["bsr_beauty"].notna()][
            ["date", "brand", "product", "bsr_beauty"]].copy()
        if len(bs):
            bs["label"] = bs["brand"] + " " + bs["product"].str.slice(0, 12)
            bs = bs.groupby(["date", "label"], as_index=False)["bsr_beauty"].min()
            bs["date_dt"] = pd.to_datetime(bs["date"])
            base_b = alt.Chart(bs).encode(
                x=alt.X("date_dt:T", title="관측일",
                        scale=alt.Scale(domain=_tdom(bs["date_dt"])),
                        axis=alt.Axis(format="%m/%d", tickCount="day",
                                      labelAngle=0)),
                y=alt.Y("bsr_beauty:Q", title="BSR (뷰티 전체) — 높을수록 좋음",
                        scale=alt.Scale(reverse=True)),
                color=alt.Color("label:N", title=None,
                                scale=_kscale(bs["label"].unique()),
                                legend=cleg))
            ln_b = base_b.mark_line(size=2.5, point=alt.OverlayMarkDef(size=70))
            tx_b = base_b.mark_text(dy=-12, fontSize=11, color="#c6d0de").encode(
                text=alt.Text("bsr_beauty:Q", format=",.0f"))
            st.altair_chart((ln_b + tx_b).properties(height=380),
                            use_container_width=True)
            st.caption("**읽는법**: BSR은 매시간 갱신 — '월구매' 표시값보다 먼저 "
                       "움직이는 조기 신호. 선이 위로 가면(순위 숫자 하락) 판매 "
                       "가속. 주의: 순위는 상대값이라 Q4 선물 시즌엔 순위 유지만 "
                       "해도 판매는 늘고 있는 것. 스냅샷마다 기록 — 주 2~3회 "
                       "'아마존 스냅샷 갱신해줘'로 촘촘하게 쌓을 수 있음.")

        # ⑤ 롤링 신호 — 직전 스냅샷 대비 구간 변화
        sub("⑤ 롤링 신호 — 구간 변화 감지",
            "롤링 30일 값이 오르면: 최근 7일 판매가 약 5주 전 같은 7일보다 강함")
        sig = []
        for lab, g in hist.sort_values("date_dt").groupby("label"):
            if len(g) < 2:
                continue
            pv, cv = g["bought_month"].iloc[-2], g["bought_month"].iloc[-1]
            sig.append({"제품": lab,
                        "직전": f"{pv:,.0f}+", "최신": f"{cv:,.0f}+",
                        "신호": ("▲ 가속" if cv > pv
                                 else ("▼ 감속" if cv < pv else "＝ 구간 유지"))})
        if sig:
            st.dataframe(pd.DataFrame(sig), hide_index=True,
                         use_container_width=True)
        st.caption("**읽는법**: 롤링 30일 값의 변화 = (새로 들어온 최근 7일) − "
                   "(빠져나간 5주 전 7일). 그래서 값이 오르면 가속, 내리면 감속 "
                   "신호. 단 표시값이 5만+ 같은 구간 단위라 구간 안 움직임은 안 "
                   "보임 — ③번 리뷰 방식이 그 빈틈을 메움.")

st.info("**갱신 방법** — ① 구글 트렌드: 매일 배치 자동. ② 아마존: 주 1회 "
        "amazon.com에서 'centellian24' 검색 → 각 제품의 평점·리뷰 수·'지난달 "
        "구매횟수'·가격을 `data/cosmetics/manual_amazon.csv`에 한 줄씩 추가 "
        "(제가 해드릴 수 있음 — '아마존 스냅샷 갱신해줘'라고 하면 됨). "
        "③ 자동화를 원하면 **Keepa API** (€49/월, 판매랭크·리뷰 이력 제공) 구독 — "
        "kbeauty 접근성 검토에서 권장했던 정식 경로.")

st.divider()
st.caption("데이터: 구글 트렌드(주간, 미국, 상대값) 자동 · 아마존 수동 스냅샷 "
           "(약관 준수). 검색 관심도는 판매량이 아니라 수요의 방향 지표.")
