# -*- coding: utf-8 -*-
"""K뷰티 브랜드 검색 모멘텀 스크리너 — 누가 뜨고 누가 지는가.

데이터: python cosmetics_absvol_update.py (월 1회, 15일 이후) → python brand_screener_update.py
"""
import io
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics"
C_BAR, C_GOLD, C_RED, C_GREEN, C_GREY = "#2a78d6", "#e8c15a", "#e05252", "#3fb27f", "#8a97aa"
STAGE_COLOR = {"급성장": "#3fb27f", "성장": "#8ec9ff", "정체": "#e8c15a", "둔화": "#eb6834",
               "쇠퇴": "#e05252", "데이터 부족": "#5f7089"}
STAGE_ORDER = ["급성장", "성장", "정체", "둔화", "쇠퇴", "데이터 부족"]
# 상장사와 브랜드 연결 — 커버리지에서 바로 쓰려고
LISTED = {"madeca cream": "동국제약 (086450)", "reedle shot": "동국제약 (086450)",
          "atopalm": "네오팜 (092730)", "medicube": "에이피알 (278470)", "anua": "더파운더즈 (비상장)",
          "cosrx": "코스알엑스 (아모레 연결)", "skin1004": "크레이버 (비상장)",
          "beauty of joseon": "구다이글로벌 (비상장)", "tirtir": "구다이글로벌 (비상장)",
          "d'alba": "달바글로벌 (483650)", "manyo": "마녀공장 (439090)", "torriden": "토리든 (비상장)",
          "numbuzin": "비나우 (비상장)", "round lab": "서린컴퍼니 (비상장)", "abib": "포컴퍼니 (비상장)",
          "mixsoon": "파켓 (비상장)", "biodance": "뷰티셀렉션 (비상장)", "laneige": "아모레퍼시픽 (090430)",
          "isntree": "이즈앤트리 (비상장)"}

st.set_page_config(page_title="K뷰티 브랜드 스크리너", page_icon="💄", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("beauty")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 6px 12px; margin: 0.9rem 0 0.5rem 0; }
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
/* 멀티셀렉트 칩: 이름이 잘리지 않게 줄바꿈시키고 글자 폭 제한을 푼다 */
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
    return pd.read_csv(p) if p.exists() else None


def get(name):
    return load(name, _stamp(name))


t = get("brand_screener.csv")
mv = get("absvol_monthly.csv")


@st.cache_data(show_spinner=False)
def _combined(stamp, stamp_g):
    """차트용 월별 시리즈 = 본 데이터 + 구글애즈로 먼저 받은 최신 달 (PM 2026-10-15 "9월꺼 왜 없어")."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from absvol_nowcast import combined
    return combined(load("absvol_monthly.csv", stamp), load("absvol_gads.csv", stamp_g))


mv = _combined(_stamp("absvol_monthly.csv"), _stamp("absvol_gads.csv"))
_gads_month = (sorted(mv.loc[mv["source"] == "gads", "month"].unique())
               if mv is not None and "source" in mv else [])
meta = json.loads((DATA / "brand_screener_meta.json").read_text(encoding="utf-8")) \
    if (DATA / "brand_screener_meta.json").exists() else {}
if t is None:
    st.error("데이터가 없습니다 — python brand_screener_update.py 를 실행하세요.")
    st.stop()

st.title("💄 K뷰티 브랜드 검색 스크리너")
st.caption(f"브랜드 {meta.get('n_brands', '—')}개 × {meta.get('n_geos', '—')}개국 · 최신 {meta.get('last_month', '—')} · "
           "구글 애즈 월 검색수(DataForSEO) · 검색량은 매출의 **선행지표**로 봄 — 돈이 아니라 관심의 크기임")

geos = t[["geo", "geo_kr"]].drop_duplicates().sort_values("geo_kr")
c1, c2 = st.columns([1, 3])
with c1:
    gk = st.selectbox("국가", geos["geo_kr"].tolist(),
                      index=geos["geo_kr"].tolist().index("미국") if "미국" in geos["geo_kr"].tolist() else 0,
                      key="bs_geo")
geo = geos[geos["geo_kr"] == gk]["geo"].iloc[0]
g = t[t["geo"] == geo].sort_values("rank").copy()
g["상장사"] = g["brand"].map(LISTED).fillna("")

k1, k2, k3, k4 = st.columns(4)
top = g.iloc[0]
k1.metric("1위 (종합점수)", top["brand"], f"{top['stage']} · 12M {top['m12']:+.0%}", delta_color="off")
rise = g[g["stage"].isin(["급성장", "성장"])]
k2.metric("뜨는 브랜드", f"{len(rise)}개", " · ".join(rise["brand"].head(3)), delta_color="off")
fall = g[g["stage"].isin(["둔화", "쇠퇴"])]
k3.metric("지는 브랜드", f"{len(fall)}개", " · ".join(fall["brand"].head(3)) or "없음", delta_color="off")
k4.metric("시장 합계 검색수", f"{g['now'].sum():,.0f}", f"{gk} · {g['last_month'].iloc[0]}", delta_color="off")

# ── 원본 엑셀 내려받기 (국가 전체 + 월별 원본)
@st.cache_data(show_spinner=False)
def make_xlsx(stamp, geo_sel):
    """엑셀 한 파일: ①선택국가 순위 ②전체 국가 ③월별 원본(선택국가) ④읽는법."""
    buf = io.BytesIO()
    sel = t[t["geo"] == geo_sel].sort_values("rank").copy()
    sel["상장사"] = sel["brand"].map(LISTED).fillna("")
    raw = mv[mv["geo"] == geo_sel].copy() if mv is not None else pd.DataFrame()
    piv = (raw.groupby(["brand", "month"], as_index=False)["searches"].sum()
              .pivot(index="brand", columns="month", values="searches")) if len(raw) else pd.DataFrame()
    guide = pd.DataFrame({"항목": [
        "출처", "단위", "m1 / m3 / m12", "vs_peak", "stage", "score", "한계 ①", "한계 ②", "한계 ③"], "설명": [
        "DataForSEO · 구글 애즈 월 검색수 (Google Ads Keyword Planner 기반)",
        "월 검색수 (건). 매출이 아니라 '관심의 크기' — 매출의 선행지표로 쓸 것",
        "1·3·12개월 전 대비 증감률. 양쪽 다 3개월 평균으로 비교(계단식 값의 노이즈 완화)",
        "최근월 ÷ 자기 역대 최고치. 1.00 = 지금이 최고, 0.30 = 전성기의 30%",
        "급성장(피크대비≥0.9 & 12M≥+30%) / 성장(12M≥+10%) / 정체(±10%) / 둔화(12M<−10%) / 쇠퇴(피크대비<0.5)",
        "3개월 모멘텀 30% + 12개월 모멘텀 50% + 피크 대비 20%, 국가 안에서 백분위로 환산한 0~100",
        "구글 애즈 값은 계단식(1,300→1,600→2,400) — 1개월 변화는 노이즈가 큼",
        "중국·한국 내수는 구글 점유율이 낮아 빠져 있음",
        "일본은 야후재팬 검색이 빠져 일관되게 과소집계 (브랜드 간 비교에는 문제 없음)"]})
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        sel.to_excel(w, sheet_name=f"순위_{geo_sel}", index=False)
        t.sort_values(["geo", "rank"]).to_excel(w, sheet_name="전체국가", index=False)
        if len(piv):
            piv.to_excel(w, sheet_name=f"월별원본_{geo_sel}")
        guide.to_excel(w, sheet_name="읽는법", index=False)
        for ws in w.book.worksheets:                      # 집 서식: Arial 8pt, 제목 10pt
            for row in ws.iter_rows():
                for c in row:
                    c.font = c.font.copy(name="Arial", size=8)
            for c in ws[1]:
                c.font = c.font.copy(name="Arial", size=10, bold=True)
            ws.freeze_panes = "B2"
    return buf.getvalue()


with c2:
    st.write("")
    st.download_button(
        "⬇️ 원본 엑셀 내려받기",
        make_xlsx(_stamp("brand_screener.csv"), geo),
        file_name=f"Kbeauty_brand_screener_{geo}_{meta.get('last_month', '')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="4개 시트: 선택 국가 순위 · 전체 국가 · 월별 원본(브랜드 × 월) · 읽는법",
        use_container_width=False)

tab1, tab2, tab3 = st.tabs(["🏁 순위표", "📈 모멘텀 지도", "🔎 브랜드 상세"])


@st.cache_data(show_spinner=False)
def _nowcast(stamp, stamp_g):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from absvol_nowcast import nowcast
    return nowcast(load("absvol_monthly.csv", stamp), load("absvol_gads.csv", stamp_g))


with tab1:
    # 최신 달 속보 (PM 2026-10-15): 본 데이터(나라별 8년치)보다 새 달이 있으면 보임. 원본과 섞지 않음.
    # 1순위 = 구글애즈 나라별 실측(absvol_gads.csv, python absvol_gads_pull.py ALL) · 2순위 = 전세계 비율 추정
    _nc = _nowcast(_stamp("absvol_monthly.csv"), _stamp("absvol_gads.csv"))
    if len(_nc):
        _m = _nc["month"].iloc[0]
        _real = (_nc["trust"] == "실측").all()
        _partial = _real and str(_nc["why"].iloc[0]).startswith("본 데이터")
        sub(f"📌 {_m[:4]}년 {int(_m[5:])}월 "
            + ("(본 데이터 수신 · 일부 구글애즈 보완)" if _partial else "(구글애즈 실측)" if _real else "속보 (추정)"),
            (str(_nc["why"].iloc[0]) + " · 순위표·점수에는 본 데이터 행만 들어감") if _partial else
            ("본 데이터(8년치)에는 아직 없는 달을 구글애즈 엔드포인트로 먼저 받음 · 같은 출처라 값이 같음 · "
             "순위표·점수에는 아직 안 들어감") if _real else
            "전세계 숫자가 먼저 나와서, 나라별 숫자가 나오기 전에 방향만 미리 봄 · 순위표·점수에는 안 들어감")
        _nc = _nc.copy()
        _nc["_o"] = _nc["brand"].map(lambda b: 0 if b == "madeca cream" else 1)
        _nc = _nc.sort_values(["_o", "trust", "c16_est"], ascending=[True, True, False])
        _show = pd.DataFrame({
            "브랜드": _nc["brand"], "믿음": _nc["trust"],
            "전세계 전월": _nc["ww_prev"].map("{:,.0f}".format),
            "전세계 이번 달": _nc["ww_now"].map("{:,.0f}".format),
            "전세계 전월 대비": _nc["ww_mom"].map("{:+.0%}".format),
            "16개국 전월 (실제)": _nc["c16_prev"].map("{:,.0f}".format),
            "16개국 이번 달 (추정)": _nc["c16_est"].map("{:,.0f}".format),
            "이유": _nc["why"]})
        st.dataframe(_show, hide_index=True, use_container_width=True, height=min(38 * (len(_show) + 1), 420))
        st.caption("16개국 추정 = 전세계 이번 달 × (겹치는 최근 3개월의 '16개국 합 ÷ 전세계' 평균). "
                   "두 숫자는 출처가 달라 크기가 다르기 때문에 비율로 맞춤. 믿음 '보통' 인 검색어 1개 브랜드는 "
                   "구글이 계단 값으로 반올림해서 0% 나 −18% 로만 움직입니다 — 실제 변화가 아닐 수 있음. "
                   "전년 대비는 나라별 숫자가 나와야 계산됩니다.")

with tab1:
    sub("검색 모멘텀 순위", "종합점수 = 3개월 모멘텀 30% + 12개월 모멘텀 50% + 피크 대비 20% (국가 안 백분위)")
    show = g[["rank", "brand", "상장사", "stage", "now", "m1", "m3", "m12", "vs_peak", "peak_month",
              "since_peak", "score"]].rename(columns={
        "rank": "순위", "brand": "브랜드", "stage": "단계", "now": "월 검색수", "m1": "1개월",
        "m3": "3개월", "m12": "12개월", "vs_peak": "피크 대비", "peak_month": "피크 시점",
        "since_peak": "피크 후 개월", "score": "점수"})
    st.dataframe(show, hide_index=True, use_container_width=True, height=60 + 35 * len(show),
                 column_config={
                     "월 검색수": st.column_config.NumberColumn(format="%,.0f"),
                     "1개월": st.column_config.NumberColumn(format="%+.0f%%"),
                     "3개월": st.column_config.NumberColumn(format="%+.0f%%"),
                     "12개월": st.column_config.NumberColumn(format="%+.0f%%"),
                     "피크 대비": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                     "점수": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100)})
    st.caption("**읽는법**: 피크 대비 1.00 = 지금이 역대 최고. 0.3 이면 전성기의 30%밖에 안 됨. "
               "12개월이 플러스인데 피크 대비가 낮으면 '바닥에서 올라오는 중', 둘 다 높으면 '한창 때'.")

with tab2:
    sub("모멘텀 지도", "오른쪽 위 = 지금도 최고치이고 계속 크는 브랜드 · 왼쪽 아래 = 식은 브랜드")
    gg = g.dropna(subset=["m12", "vs_peak"]).copy()
    gg["크기"] = gg["now"]
    base = alt.Chart(gg).encode(
        x=alt.X("m12:Q", title="12개월 검색 증감", axis=alt.Axis(format="%")),
        y=alt.Y("vs_peak:Q", title="자기 피크 대비", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1.1])),
        tooltip=["brand", "상장사", "stage", alt.Tooltip("now", title="월 검색수", format=",.0f"),
                 alt.Tooltip("m3", title="3개월", format="+.0%"), alt.Tooltip("m12", title="12개월", format="+.0%"),
                 alt.Tooltip("vs_peak", title="피크 대비", format=".0%"), "peak_month"])
    pts = base.mark_circle(opacity=0.85).encode(
        size=alt.Size("크기:Q", title="월 검색수", scale=alt.Scale(range=[80, 1800]), legend=None),
        color=alt.Color("stage:N", title="단계", scale=alt.Scale(domain=STAGE_ORDER,
                        range=[STAGE_COLOR[s] for s in STAGE_ORDER]), legend=alt.Legend(orient="top")))
    lab = base.mark_text(dy=-14, fontSize=11, color="#dde5f0").encode(text="brand:N")
    z = alt.Chart(pd.DataFrame({"v": [0]})).mark_rule(color="#667", strokeDash=[4, 3]).encode(x="v:Q")
    h = alt.Chart(pd.DataFrame({"v": [0.5]})).mark_rule(color="#667", strokeDash=[4, 3]).encode(y="v:Q")
    st.altair_chart(alt.layer(z, h, pts, lab).properties(height=520), use_container_width=True)
    st.caption("원 크기 = 월 검색수(브랜드의 절대 크기). 큰 원이 오른쪽 위에 있으면 가장 강한 브랜드임.")

with tab3:
    sub("브랜드 상세", "x축·표시 방식을 골라서 봄 · 센텔리안24(madeca cream)는 굵은 금색")
    # 브랜드는 칩이 많아 좁은 칸에서 이름이 잘림 → 한 줄 통째로 씀 (PM 2026-10-08)
    d1, d2 = st.columns([2.2, 1.2])
    with d1:
        gsel = st.multiselect("국가 (여러 개 가능)", geos["geo_kr"].tolist(), default=[gk], key="bs_geos",
                              help="여러 나라를 고르면 선은 '브랜드 · 국가' 로 나뉩니다. 합쳐 보려면 '국가 합산'을 켜세요.")
    with d2:
        mode = st.radio("세로축", ["절대량 (월 검색수)", "상대 (자기 피크=100)"], index=0, key="bs_mode",
                        horizontal=True,
                        help="상대 = 브랜드마다 자기 최고치를 100으로 맞춤 — 크기가 다른 브랜드의 '모양'을 비교할 때. "
                             "절대량 = 실제 월 검색수 — 누가 큰지 볼 때.")
    # 기본 브랜드 4개 (PM 2026-10-22): 센텔리안24(madeca cream) · 코스알엑스 · 리들샷 · 아누아. 없으면 순위 상위로 채움
    _DEFAULT_BRANDS = ["madeca cream", "cosrx", "reedle shot", "anua"]
    _opts = sorted(t["brand"].unique())
    _default = [b for b in _DEFAULT_BRANDS if b in _opts] or g["brand"].head(4).tolist()
    pick = st.multiselect("브랜드 (여러 개 가능)", _opts,
                          default=_default, key="bs_pick",
                          help="브랜드 이름이 길어 한 줄을 다 씁니다. 많이 고르면 칩이 여러 줄로 쌓입니다.")
    gcodes = geos[geos["geo_kr"].isin(gsel)]["geo"].tolist()
    x1, x2, x3 = st.columns([1.7, 1.1, 1.1])
    with x1:
        xmode = st.radio("가로축", ["실제 날짜 (연·월)", "성장 시작 후 개월 (t=0 정렬)"], index=1, key="bs_xmode",
                         horizontal=True,
                         help="실제 날짜 = 같은 시점에 무슨 일이 있었는지 볼 때. "
                              "t=0 정렬 = 브랜드마다 뜨기 시작한 달을 0으로 맞춰 '수명주기 모양'을 겹쳐 볼 때 "
                              "(t=0 = 자기 피크의 10%에 처음 닿은 달).")
    with x2:
        merge_geo = st.toggle("국가 합산", value=len(gcodes) > 1, key="bs_merge",
                              help="고른 나라를 더해서 브랜드당 한 선으로 봅니다.")
    with x3:
        logy = st.toggle("로그 축", value=False, key="bs_log", help="브랜드 간 크기 차이가 아주 클 때")
    _allm = sorted(mv["month"].unique()) if mv is not None else []
    _t0mode = xmode.startswith("성장")
    _nmax = len(_allm) if _allm else 24
    if _t0mode:
        _PRE = {"초기 1년 (0~12)": 12, "초기 2년 (0~24)": 24, "초기 3년 (0~36)": 36,
                "5년 (0~60)": 60, "전체": 999}
        _hint = "브랜드마다 수명이 달라 긴 브랜드가 x축을 늘리면 초반이 눌려 보입니다. 구간을 좁히면 뜨는 국면을 크게 봅니다."
    else:
        _PRE = {"최근 1년": 12, "최근 2년": 24, "최근 3년": 36, "최근 5년": 60, "전체": _nmax}
        _hint = "월·연 2단 축은 기간이 짧을수록 읽기 쉽습니다."
    sp1, sp2 = st.columns([1.6, 2.4])
    with sp1:
        _zk = st.radio("구간", list(_PRE), index=(len(_PRE) - 1) if _t0mode else 1, horizontal=True, key="bs_span", help=_hint)
    if st.session_state.get("_bs_span_prev") != (_zk, _t0mode):   # 프리셋·모드가 바뀌면 슬라이더도 맞춤
        st.session_state["_bs_span_prev"] = (_zk, _t0mode)
        st.session_state.pop("bs_range", None)
    with sp2:
        if _t0mode:
            _lo, _hi = st.slider("직접 범위 (성장 시작 후 개월)", 0, 120, (0, min(_PRE[_zk], 120)), 1, key="bs_range")
            nmon = _nmax
        else:
            nmon = st.slider("직접 범위 (최근 몇 개월)", 12, _nmax, min(_PRE[_zk], _nmax), 1, key="bs_range")
            _lo, _hi = 0, 999

    if pick and gcodes and mv is not None:
        m = mv[mv["geo"].isin(gcodes) & mv["brand"].isin(pick)].copy()
        if merge_geo:
            m = m.groupby(["brand", "month"], as_index=False)["searches"].sum()
            m["키"] = m["brand"]
        else:
            m = m.groupby(["geo", "brand", "month"], as_index=False)["searches"].sum()
            m["키"] = m["brand"] + " · " + m["geo"]
        m["dt"] = pd.to_datetime(m["month"] + "-01")
        if _allm and nmon < len(_allm):              # 최근 N개월만
            m = m[m["month"] >= _allm[-nmon]]
        rel = mode.startswith("상대")
        if rel:
            m["값"] = m.groupby("키")["searches"].transform(lambda x: x / x.max() * 100 if x.max() > 0 else 0)
            ytitle = "검색 관심도 (자기 피크=100)"
        else:
            m["값"] = m["searches"]
            ytitle = "월 검색수 (구글 애즈, 절대량)"

        t0 = xmode.startswith("성장")
        if t0:                       # 성장 시작(자기 피크의 10% 첫 도달) 기준으로 각 선을 0에 맞춤
            keep = []
            for k, gg in m.sort_values("dt").groupby("키"):
                pk = gg["searches"].max()
                if pk <= 0:
                    continue
                br = gg[gg["searches"] >= pk * 0.10]
                if not len(br):
                    continue
                b0 = br["dt"].iloc[0]
                gg = gg[gg["dt"] >= b0].copy()
                gg["t"] = ((gg["dt"].dt.year - b0.year) * 12 + (gg["dt"].dt.month - b0.month))
                gg["성장시작"] = b0.strftime("%Y-%m")
                keep.append(gg)
            if not keep:
                st.caption("성장 시작 시점을 찾지 못했습니다.")
                st.stop()
            m = pd.concat(keep)
            m = m[(m["t"] >= _lo) & (m["t"] <= _hi)]

        keys = sorted(m["키"].unique())
        PAL = ["#2a78d6", "#8ec9ff", "#4fb8c9", "#eb6834", "#b06fc9", "#4fb862", "#e8425a",
               "#b5b5b5", "#2fa89a", "#d98cb3", "#7a8ff0", "#c9a34f", "#5f7089", "#9fd65f"]
        cols, pi = [], 0
        for k in keys:
            if k.startswith("madeca cream"):
                cols.append(C_GOLD)
            else:
                cols.append(PAL[pi % len(PAL)])
                pi += 1
        m["굵기"] = np.where(m["키"].str.startswith("madeca cream"), 4.0, 1.9)
        yenc = alt.Y("값:Q", title=ytitle,
                     scale=alt.Scale(type="log" if logy and not rel else "linear", zero=not logy))
        cenc = alt.Color("키:N", title=None, scale=alt.Scale(domain=keys, range=cols),
                         legend=alt.Legend(orient="top", columns=4))
        senc = alt.Size("굵기:Q", scale=alt.Scale(domain=[1.9, 4.0], range=[1.9, 4.0]), legend=None)
        tips = ["키", alt.Tooltip("month:N", title="연월"),
                alt.Tooltip("searches:Q", title="월 검색수", format=",.0f")] \
            + ([alt.Tooltip("값:Q", title="피크 대비", format=".0f")] if rel else []) \
            + ([alt.Tooltip("t:Q", title="성장 시작 후 개월"), alt.Tooltip("성장시작:N", title="성장 시작 달")] if t0 else [])

        if t0:
            ch = alt.Chart(m).mark_line().encode(
                x=alt.X("t:Q", title="성장 시작 후 개월 (t=0 = 검색이 자기 최고치의 10%에 처음 닿은 달)",
                        axis=alt.Axis(tickMinStep=2, labelAngle=0)),
                y=yenc, color=cenc, size=senc, tooltip=tips)
            st.altair_chart(ch.properties(height=470), use_container_width=True)
        else:
            # 2단 가로축: 한 축에 2줄 라벨 (위=월, 아래=연도). vconcat 축 띠는 폭이 안 맞아 차트가
            # 화면 밖으로 삐져나가서 버림 (PM 2026-10-08). labelExpr 가 배열을 주면 Vega 가 2줄로 그림.
            nmon_shown = m["month"].nunique()
            step = 1 if nmon_shown <= 30 else (2 if nmon_shown <= 60 else 3)
            # tickCount 가 이미 간격을 솎아 주므로 라벨은 단순하게: 윗줄 = 월, 아랫줄 = 1월일 때만 연도
            lbl = ("[timeFormat(datum.value, '%m'), "
                   "timeFormat(datum.value, '%m') == '01' ? timeFormat(datum.value, '%Y') : '']")
            x_ax = alt.Axis(tickCount={"interval": "month", "step": step}, labelAngle=0, title=None,
                            labelExpr=lbl, labelFontSize=10, labelColor="#c6d2e3",
                            labelLineHeight=14, labelPadding=4, grid=False)
            jan = pd.DataFrame({"jan": pd.date_range(m["dt"].min(), m["dt"].max(), freq="YS")})
            line = alt.Chart(m).mark_line().encode(
                x=alt.X("dt:T", title=None, axis=x_ax), y=yenc, color=cenc, size=senc, tooltip=tips)
            vline = alt.Chart(jan).mark_rule(color="#33415c", strokeDash=[2, 3]).encode(x="jan:T")
            st.altair_chart(alt.layer(vline, line).properties(height=470), use_container_width=True)
            st.caption("가로축 2단 — 윗줄 = 월(01~12), 아랫줄 = 연도(1월 자리에 표시). 세로 점선 = 해가 바뀌는 지점."
                       + (f"  ·  라벨이 겹치지 않게 {step}개월마다 표시합니다." if step > 1 else ""))

        st.caption(("**상대**: 브랜드마다 자기 최고치를 100으로 맞춘 '모양' 비교 — 크기가 달라도 흐름을 겹쳐 볼 수 있음."
                    if rel else
                    "**절대량**: 실제 월 검색수 — 누가 더 큰 브랜드인지 보임.")
                   + ("  **t=0 정렬**: 브랜드마다 검색이 뜨기 시작한 달(자기 최고치의 10%)을 0으로 맞춰 수명주기 모양을 비교합니다." if t0
                      else "  **실제 날짜**: 같은 시점에 무슨 일이 있었는지 봅니다.")
                   + " 금색 굵은 선 = 센텔리안24(madeca cream, 동국제약)."
                   + (f"  **{', '.join(_gads_month)} 은 본 데이터에 아직 빈 나라·브랜드만 구글애즈로 보완한 값**"
                      "(같은 출처 · 본 데이터에 있는 검색어만 이어 붙임)." if _gads_month else ""))

        tb = t[t["brand"].isin(pick) & t["geo"].isin(gcodes)].copy()
        tb["상장사"] = tb["brand"].map(LISTED).fillna("")
        st.dataframe(tb[["geo_kr", "brand", "상장사", "stage", "now", "m3", "m12", "vs_peak", "peak_month"]]
                     .sort_values(["geo_kr", "brand"])
                     .rename(columns={"geo_kr": "국가", "brand": "브랜드", "stage": "단계", "now": "월 검색수",
                                      "m3": "3개월", "m12": "12개월", "vs_peak": "피크 대비",
                                      "peak_month": "피크 시점"}),
                     hide_index=True, use_container_width=True,
                     column_config={"월 검색수": st.column_config.NumberColumn(format="%,.0f"),
                                    "3개월": st.column_config.NumberColumn(format="%+.0f%%"),
                                    "12개월": st.column_config.NumberColumn(format="%+.0f%%"),
                                    "피크 대비": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.caption("국가와 브랜드를 하나 이상 고르세요.")

    # ================= 일본시장 K-beauty 따로 보기 (PM 2026-10-22) =================
    # 일본은 구글 점유율이 낮아(야후재팬·빙) 검색량만으로 부족 → 판매·입소문 랭킹을 같이 본다.
    # 데이터: jp_kbeauty_update.py (매일) → data/cosmetics/jp_cosme_rank.csv, jp_qoo10_rank.csv
    st.divider()
    sub("일본시장 K-beauty 따로 보기",
        "@cosme 주간 TOP100 (입소문) + Qoo10 Japan ビューティ 베스트셀러 TOP200 (판매) 에서 한국 브랜드만 추림 · 매일 수집")
    _jc = load("jp_cosme_rank.csv", _stamp("jp_cosme_rank.csv"))
    _jq = load("jp_qoo10_rank.csv", _stamp("jp_qoo10_rank.csv"))
    _kb = load("jp_kbrands.csv", _stamp("jp_kbrands.csv"))
    if _jc is None or _jq is None or _kb is None:
        st.info("아직 일본 랭킹 데이터가 없습니다 — `python jp_kbeauty_update.py` 를 먼저 실행하세요.")
    else:
        for _d in (_jc, _jq):
            _d["kbrand"] = _d["kbrand"].fillna("")
        _kname = dict(zip(_kb["key"], _kb["name_kr"]))
        _klist = dict(zip(_kb["key"], _kb["listed"]))
        _cw = sorted(_jc["period_start"].unique())
        _qd = sorted(_jq["date"].unique())
        _c_now = _jc[_jc["period_start"] == _cw[-1]]
        _c_prev = _jc[_jc["period_start"] == _cw[-2]] if len(_cw) > 1 else None
        _q_now = _jq[_jq["date"] == _qd[-1]]
        _q_prev = _jq[_jq["date"] == _qd[-2]] if len(_qd) > 1 else None
        _kc = _c_now[_c_now["kbrand"] != ""]
        _kq = _q_now[_q_now["kbrand"] != ""]
        j1, j2, j3, j4 = st.columns(4)
        j1.metric("@cosme TOP100 안 한국 제품", f"{len(_kc)}개",
                  (f"전주 {int((_c_prev['kbrand'] != '').sum())}개" if _c_prev is not None else None), delta_color="off")
        j2.metric("Qoo10 뷰티 TOP200 안 한국 제품", f"{len(_kq)}개",
                  (f"전일 {int((_q_prev['kbrand'] != '').sum())}개" if _q_prev is not None else "첫 수집"), delta_color="off")
        j3.metric("Qoo10 TOP50 안 한국 제품", f"{int((_kq['rank'] <= 50).sum())}개",
                  f"{_qd[-1]} 기준", delta_color="off")
        j4.metric("@cosme 집계 주간", f"{_c_now['period_start'].iloc[0][5:]}~{_c_now['period_end'].iloc[0][5:]}",
                  "매주 금요일 갱신", delta_color="off")

        # 브랜드별 요약: 두 랭킹에서 몇 개·최고 몇 위
        def _brand_tbl(df, col_prev=None):
            g = df[df["kbrand"] != ""].groupby("kbrand").agg(n=("rank", "size"), best=("rank", "min")).reset_index()
            if col_prev is not None and len(col_prev):
                p = col_prev[col_prev["kbrand"] != ""].groupby("kbrand").agg(n_prev=("rank", "size"), best_prev=("rank", "min")).reset_index()
                g = g.merge(p, on="kbrand", how="outer")
            return g
        _bc = _brand_tbl(_c_now, _c_prev).rename(columns={"n": "@cosme 개수", "best": "@cosme 최고", "n_prev": "@cosme 전주", "best_prev": "@cosme 전주 최고"})
        _bq = _brand_tbl(_q_now, _q_prev).rename(columns={"n": "Qoo10 개수", "best": "Qoo10 최고", "n_prev": "Qoo10 전일", "best_prev": "Qoo10 전일 최고"})
        _bb = _bc.merge(_bq, on="kbrand", how="outer").fillna({"@cosme 개수": 0, "Qoo10 개수": 0})
        _bb["브랜드"] = _bb["kbrand"].map(lambda k: f"{_kname.get(k, k)} ({k})")
        _bb["상장사"] = _bb["kbrand"].map(_klist).fillna("")
        _bb["_score"] = _bb["Qoo10 개수"].fillna(0) * 2 + _bb["@cosme 개수"].fillna(0) * 3
        _cols = ["브랜드", "상장사", "Qoo10 개수", "Qoo10 최고", "@cosme 개수", "@cosme 최고"]
        for extra in ("Qoo10 전일 최고", "@cosme 전주 최고"):
            if extra in _bb.columns:
                _cols.append(extra)
        st.dataframe(_bb.sort_values(["_score", "Qoo10 최고"], ascending=[False, True])[_cols], hide_index=True,
                     use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%.0f") for c in _cols[2:]})
        st.caption("개수 = 그 랭킹 안에 든 제품 수, 최고 = 가장 높은 순위. Qoo10은 판매(가격·쿠폰 영향 큼), @cosme는 리뷰·관심(입소문). "
                   "브랜드 판정은 `data/cosmetics/jp_kbrands.csv` 별칭(영문·가타카나) 기준 — 빠진 브랜드가 있으면 거기에 한 줄 추가.")

        _t1, _t2, _t3 = st.tabs(["Qoo10 한국 제품 목록", "@cosme 한국 제품 목록", "추이 (쌓이는 중)"])
        with _t1:
            _v = _kq[["rank", "delta", "brand", "title", "price", "rating", "reviews", "kbrand"]].copy()
            _v["kbrand"] = _v["kbrand"].map(lambda k: _kname.get(k, k))
            _v["delta"] = _v["delta"].map({"up": "▲", "down": "▼", "same": "–", "new": "NEW"}).fillna("")
            st.dataframe(_v.rename(columns={"rank": "순위", "delta": "변동", "brand": "셀러/브랜드", "title": "상품", "price": "가격(엔)",
                                            "rating": "평점", "reviews": "리뷰수", "kbrand": "브랜드(KR)"}),
                         hide_index=True, use_container_width=True, height=min(38 * (len(_v) + 1), 520),
                         column_config={"가격(엔)": st.column_config.NumberColumn(format="%,.0f"),
                                        "리뷰수": st.column_config.NumberColumn(format="%,.0f")})
            st.caption(f"Qoo10 Japan ビューティ 베스트셀러 TOP200 · {_qd[-1]} 수집 · 전체 {len(_q_now)}개 중 한국 {len(_kq)}개. "
                       "셀러명이 브랜드가 아닌 경우(대리점)는 상품명에서 브랜드를 찾음.")
        with _t2:
            _v = _kc[["rank", "status", "brand", "product", "category", "rating", "votes", "price", "kbrand"]].copy()
            _v["kbrand"] = _v["kbrand"].map(lambda k: _kname.get(k, k))
            _v["status"] = _v["status"].map({"up": "▲", "down": "▼", "stay": "–", "new": "NEW"}).fillna("")
            st.dataframe(_v.rename(columns={"rank": "순위", "status": "변동", "brand": "브랜드", "product": "제품", "category": "카테고리",
                                            "rating": "평점(7점)", "votes": "리뷰수", "price": "가격", "kbrand": "브랜드(KR)"}),
                         hide_index=True, use_container_width=True, height=min(38 * (len(_v) + 1), 520))
            st.caption(f"@cosme コスメ総合ランキング TOP100 · 집계 {_c_now['period_start'].iloc[0]}~{_c_now['period_end'].iloc[0]} · "
                       f"한국 {len(_kc)}개. 3주치 보관 (사이트가 지난주·지지난주까지만 공개).")
        with _t3:
            _hc = _jc.groupby("period_start").apply(lambda d: int((d["kbrand"] != "").sum())).rename("@cosme TOP100 한국 제품 수").reset_index()
            _hq = _jq.groupby("date").apply(lambda d: int((d["kbrand"] != "").sum())).rename("Qoo10 TOP200 한국 제품 수").reset_index()
            _h = pd.concat([_hc.rename(columns={"period_start": "date"}).melt("date", var_name="지표", value_name="개수"),
                            _hq.melt("date", var_name="지표", value_name="개수")])
            _h["date"] = pd.to_datetime(_h["date"])
            st.altair_chart(alt.Chart(_h).mark_line(point=True).encode(
                x=alt.X("date:T", title=None), y=alt.Y("개수:Q", title="한국 제품 수"),
                color=alt.Color("지표:N", title=None, legend=alt.Legend(orient="top")),
                tooltip=["date:T", "지표:N", "개수:Q"]).properties(height=260), use_container_width=True)
            # 브랜드별 Qoo10 최고 순위 추이
            _bh = _jq[_jq["kbrand"] != ""].groupby(["date", "kbrand"])["rank"].min().reset_index()
            if _bh["date"].nunique() > 1:
                _bh["브랜드"] = _bh["kbrand"].map(lambda k: _kname.get(k, k)); _bh["date"] = pd.to_datetime(_bh["date"])
                st.altair_chart(alt.Chart(_bh).mark_line(point=True).encode(
                    x=alt.X("date:T", title=None), y=alt.Y("rank:Q", title="Qoo10 최고 순위 (위로 갈수록 좋음)", scale=alt.Scale(reverse=True)),
                    color=alt.Color("브랜드:N", title=None), tooltip=["date:T", "브랜드:N", "rank:Q"]).properties(height=300),
                    use_container_width=True)
            st.caption("Qoo10은 히스토리가 없어 오늘부터 하루 1장씩 쌓입니다. 며칠 지나면 브랜드별 순위 추이가 보입니다. "
                       "메가와리(분기 1회 대형 세일) 기간엔 순위가 크게 흔들리니 그 주는 따로 볼 것.")
        st.caption("왜 따로 보나: 일본 검색 점유율은 구글 59% · 빙 31% · 야후재팬 8% (StatCounter 2026-09) 라 구글 검색량이 일본 전체를 다 담지 못함. "
                   "Qoo10(판매)과 @cosme(입소문)로 보완. 출처 페이지: cosme.net/ranking/products, m.qoo10.jp Bestsellers(ビューティ).")

st.caption("한계: 구글 애즈 검색수는 값이 계단식(1,300 → 1,600 → 2,400)이라 1개월 변화는 노이즈가 큼 — "
           "3·12개월을 볼 것. 중국·한국 내수는 구글 점유율이 낮아 빠져 있음. 일본은 야후재팬(점유율 약 8%)이 빠져 조금 과소집계임.")
