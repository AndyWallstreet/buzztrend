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
    pick = st.multiselect("브랜드 (여러 개 가능)", sorted(t["brand"].unique()),
                          default=g["brand"].head(4).tolist(), key="bs_pick",
                          help="브랜드 이름이 길어 한 줄을 다 씁니다. 많이 고르면 칩이 여러 줄로 쌓입니다.")
    gcodes = geos[geos["geo_kr"].isin(gsel)]["geo"].tolist()
    x1, x2, x3 = st.columns([1.7, 1.1, 1.1])
    with x1:
        xmode = st.radio("가로축", ["실제 날짜 (연·월)", "붐 시작 후 개월 (t=0 정렬)"], index=0, key="bs_xmode",
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
    nmon = st.slider("기간 (최근 몇 개월)", 12, max(24, len(_allm)), min(36, len(_allm)), 6, key="bs_months",
                     help="월·연 2단 축은 기간이 짧을수록 읽기 쉽습니다. 36개월이 기본입니다.")

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

        t0 = xmode.startswith("붐")
        if t0:                       # 붐 시작(자기 피크의 10% 첫 도달) 기준으로 각 선을 0에 맞춤
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
                gg["붐시작"] = b0.strftime("%Y-%m")
                keep.append(gg)
            if not keep:
                st.caption("붐 시작을 찾지 못했습니다.")
                st.stop()
            m = pd.concat(keep)

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
            + ([alt.Tooltip("t:Q", title="붐 후 개월"), alt.Tooltip("붐시작:N", title="붐 시작")] if t0 else [])

        if t0:
            ch = alt.Chart(m).mark_line().encode(
                x=alt.X("t:Q", title="붐 시작 후 개월 (t=0 = 자기 피크의 10% 첫 도달)",
                        axis=alt.Axis(tickMinStep=2, labelAngle=0)),
                y=yenc, color=cenc, size=senc, tooltip=tips)
            st.altair_chart(ch.properties(height=470), use_container_width=True)
        else:
            # 2단 가로축을 직접 그림 — 위 줄 = 월(01·02…), 아래 줄 = 연도 (PM 2026-10-08).
            # Vega 의 축 2개 겹치기는 라벨이 안 뜨는 경우가 있어, 축 띠를 별도 차트로 만들어 붙인다.
            months = sorted(m["month"].unique())
            ax = pd.DataFrame({"month": months})
            ax["dt"] = pd.to_datetime(ax["month"] + "-01")
            ax["mm"] = ax["dt"].dt.strftime("%m")
            ax["yy"] = ax["dt"].dt.year
            step = 1 if len(months) <= 30 else (2 if len(months) <= 60 else 3)
            ax["show_m"] = [i % step == 0 for i in range(len(ax))]
            yr = (ax.groupby("yy", as_index=False)
                    .agg(mid=("dt", lambda s_: s_.iloc[len(s_) // 2]), n=("dt", "size")))
            yr = yr[yr["n"] >= 2]                      # 한두 달짜리 해는 라벨 생략
            xsc = alt.Scale(domain=[ax["dt"].min().isoformat(), ax["dt"].max().isoformat()])
            xq = alt.X("dt:T", title=None, axis=None, scale=xsc)
            line = alt.Chart(m).mark_line().encode(x=xq, y=yenc, color=cenc, size=senc, tooltip=tips)
            vline = alt.Chart(yr.assign(jan=pd.to_datetime(yr["yy"].astype(str) + "-01-01"))).mark_rule(
                color="#33415c", strokeDash=[2, 3]).encode(x=alt.X("jan:T", axis=None, scale=xsc))
            strip_m = alt.Chart(ax[ax["show_m"]]).mark_text(
                fontSize=9, color="#9fb0c8", dy=0).encode(x=xq, text="mm:N")
            strip_y = alt.Chart(yr).mark_text(
                fontSize=13, fontWeight="bold", color="#dde5f0", dy=18).encode(
                x=alt.X("mid:T", axis=None, scale=xsc), text="yy:N")
            strip = alt.layer(strip_m, strip_y).properties(height=34)
            st.altair_chart(
                alt.vconcat(alt.layer(vline, line).properties(height=440), strip, spacing=0)
                  .configure_view(strokeOpacity=0),
                use_container_width=True)
            st.caption(f"가로축 2단 — 위 작은 숫자 = 월(01~12){'  ·  ' + str(step) + '개월마다 표시' if step > 1 else ''}, "
                       "아래 굵은 숫자 = 연도. 세로 점선 = 1월(해가 바뀌는 지점).")

        st.caption(("**상대**: 브랜드마다 자기 최고치를 100으로 맞춘 '모양' 비교 — 크기가 달라도 흐름을 겹쳐 볼 수 있음."
                    if rel else
                    "**절대량**: 실제 월 검색수 — 누가 더 큰 브랜드인지 보임.")
                   + ("  **t=0 정렬**: 브랜드마다 뜬 시점을 0으로 맞춰 수명주기 모양을 비교합니다." if t0
                      else "  **실제 날짜**: 같은 시점에 무슨 일이 있었는지 봅니다.")
                   + " 금색 굵은 선 = 센텔리안24(madeca cream, 동국제약).")

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

st.caption("한계: 구글 애즈 검색수는 값이 계단식(1,300 → 1,600 → 2,400)이라 1개월 변화는 노이즈가 큼 — "
           "3·12개월을 볼 것. 중국·한국 내수는 구글 점유율이 낮아 빠져 있음. 일본은 야후재팬이 빠져 과소집계임.")
