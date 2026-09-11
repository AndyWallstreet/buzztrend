# -*- coding: utf-8 -*-
"""한국 화장품 수출 (관세청) — Cosmetics/Beauty 섹터의 수출 데이터 페이지.

데이터: customs_fetch.py가 관세청 무역통계(tradedata.go.kr)에서 직접 수집 —
customs_monthly.csv.gz (월×국가×HS4) + customs_exports.csv (연간 집계).
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "cosmetics"

st.set_page_config(page_title="한국 화장품 수출", page_icon="🚢", layout="wide")

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


_meta = {}
if (DATA / "customs_meta.json").exists():
    _meta = json.loads((DATA / "customs_meta.json").read_text(encoding="utf-8"))
_lm = _meta.get("latest_month", "")            # 'YYYY-MM'

st.title("한국 화장품 수출 — 관세청 (직접 수집)")
st.caption(f"월 × 국가 × HS(3303~3307) · US$ · 2016.01 ~ {_lm.replace('-', '.')}"
           " 확정통계 · [💄 센텔리안24 트래커](/cosmetics-beauty)")

cx = load("customs_exports.csv", _stamp("customs_exports.csv"))
mo = load("customs_monthly.csv.gz", _stamp("customs_monthly.csv.gz"))
im = load("customs_interim.csv", _stamp("customs_interim.csv"))
if cx is None or not len(cx):
    st.info("데이터가 없습니다 — python customs_fetch.py 실행 후 커밋.")
    st.stop()
# 확정통계가 이미 커버한 잠정월은 자동 제외 (확정으로 대체)
if im is not None and len(im) and _lm:
    im = im[im["month"] > _lm]

_ytot = cx.groupby("year")["usd_k"].sum() / 1e6          # US$bn (usd_k=US$000)
_y_full = int(cx["year"].max()) - 1                      # 마지막 완성 연도
_y_cur = int(cx["year"].max())
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"{_y_full}년 수출 총액", f"${_ytot[_y_full]:,.2f}bn",
          f"{(_ytot[_y_full] / _ytot[_y_full - 1] - 1) * 100:+.1f}% YoY",
          delta_color="normal")
_top_c = (cx[cx["year"] == _y_full].groupby("country_en")["usd_k"].sum()
          .sort_values(ascending=False))
k2.metric(f"{_y_full}년 1위 시장: {_top_c.index[0]}",
          f"${_top_c.iloc[0] / 1e6:,.2f}bn",
          f"점유 {_top_c.iloc[0] / _top_c.sum() * 100:.0f}%", delta_color="off")
if mo is not None and _lm:
    _mmax = int(_lm[5:7])
    _ycur_sum = mo[mo["month"].str[:4] == str(_y_cur)]["exp_usd_k"].sum() / 1e6
    _yprv_sum = mo[(mo["month"].str[:4] == str(_y_cur - 1))
                   & (mo["month"].str[5:7].astype(int) <= _mmax)][
        "exp_usd_k"].sum() / 1e6
    k3.metric(f"{_y_cur}년 1~{_mmax}월 누계", f"${_ycur_sum:,.2f}bn",
              f"{(_ycur_sum / _yprv_sum - 1) * 100:+.1f}% vs 전년 같은 기간",
              delta_color="normal")
else:
    k3.metric(f"{_y_cur}년 누계", f"${_ytot[_y_cur]:,.2f}bn",
              "연간 아님 — 잠정 누계", delta_color="off")
if im is not None and len(im):
    _ir = im.iloc[-1]
    k4.metric(f"{int(_ir['month'][5:7])}월 잠정*",
              f"${_ir['usd_mn'] / 1000:,.2f}bn",
              f"+{_ir['yoy_pct']:.1f}% YoY (산업부 발표)",
              delta_color="normal")
    st.caption(f"*{int(_ir['month'][5:7])}월은 확정 전 — [산업부 수출입동향]"
               f"({_ir['source']}) {_ir['published']} 발표, {_ir['basis']} 기준. "
               "MTI 분류라 HS 확정치와 소폭 다를 수 있음 — 확정통계가 나오면 "
               "자동으로 대체됨.")

# ---- 월별 추이
if mo is not None and len(mo):
    sub("월별 수출 추이 — 최근 3년", "US$mn · 주황 선 = 전년 같은 달 대비 % (YoY)")
    ms = mo.groupby("month", as_index=False)["exp_usd_k"].sum()
    ms["usd_mn"] = ms["exp_usd_k"] / 1000
    ms = ms.sort_values("month")
    ms["yoy"] = (ms["usd_mn"] / ms["usd_mn"].shift(12) - 1) * 100
    ms36 = ms.tail(36).copy()
    ms36["kind"] = "확정"
    if im is not None and len(im):
        _imd = im.rename(columns={})[["month", "usd_mn"]].copy()
        _imd["kind"] = "잠정*"
        ms36 = pd.concat([ms36, _imd], ignore_index=True)
    ms36["date"] = pd.to_datetime(ms36["month"] + "-01")
    bar_m = alt.Chart(ms36).mark_bar().encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%y %b", labelAngle=0)),
        y=alt.Y("usd_mn:Q", title="월 수출 (US$mn)"),
        color=alt.Color("kind:N", title=None,
                        scale=alt.Scale(domain=["확정", "잠정*"],
                                        range=["#2a78d6", "#e8c15a"]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("date:T", format="%Y-%m"), "kind",
                 alt.Tooltip("usd_mn:Q", format=",.0f"),
                 alt.Tooltip("yoy:Q", format="+.1f")])
    txt_i = alt.Chart(ms36[ms36["kind"] == "잠정*"]).mark_text(
        dy=-10, fontSize=11, color="#e8c15a").encode(
        x=alt.X("date:T"), y=alt.Y("usd_mn:Q"),
        text=alt.Text("usd_mn:Q", format=",.0f"))
    line_y = alt.Chart(ms36[ms36["kind"] == "확정"]).mark_line(
        color="#eb6834", size=2.5, point=True).encode(
        x=alt.X("date:T"), y=alt.Y("yoy:Q", title="YoY (%)"))
    st.altair_chart(alt.layer(bar_m + txt_i, line_y)
                    .resolve_scale(y="independent")
                    .properties(height=340), use_container_width=True)
    st.caption("**읽는법**: 파란 막대 = 확정 월 수출, 금색 막대 = 산업부 발표 "
               "잠정치(MTI 기준 — 뉴스에 먼저 나오는 숫자), 주황 선 = 확정치의 "
               "전년 같은 달 대비 %. 확정통계는 약 5주 시차로 공표됨 "
               "(7월분 → 9월 초).")

x1, x2 = st.columns(2, gap="large")
_regc = {"Asia": "#2a78d6", "North America": "#eb6834", "Europe": "#4fb862",
         "CIS": "#b06fc9", "Middle East": "#e8c15a", "Oceania": "#4fb8c9",
         "Latin America": "#e8425a", "Africa": "#b5b5b5"}
with x1:
    sub("연도별 수출 — 권역 구성", "US$mn · 막대 위 = 연 합계")
    rg = cx.groupby(["year", "region"], as_index=False)["usd_k"].sum()
    rg["usd_mn"] = rg["usd_k"] / 1000
    bars = alt.Chart(rg).mark_bar().encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("usd_mn:Q", title="수출 (US$mn)"),
        color=alt.Color("region:N", title=None,
                        scale=alt.Scale(domain=list(_regc),
                                        range=list(_regc.values())),
                        legend=alt.Legend(orient="top", columns=4)),
        tooltip=["year:O", "region", alt.Tooltip("usd_mn:Q", format=",.0f")])
    tot = rg.groupby("year", as_index=False)["usd_mn"].sum()
    txt = alt.Chart(tot).mark_text(dy=-8, fontSize=11, color="#c6d0de").encode(
        x=alt.X("year:O"), y=alt.Y("usd_mn:Q"),
        text=alt.Text("usd_mn:Q", format=",.0f"))
    st.altair_chart((bars + txt).properties(height=380),
                    use_container_width=True)
    st.caption("**읽는법**: 2022년 꺾임 = 중국(파랑 축소), 그 뒤 회복 = "
               "미국·유럽·CIS가 끌고 감 — 시장 다변화가 이번 사이클의 핵심. "
               "마지막 막대는 1~5월 누계라 짧은 게 정상.")
with x2:
    _cl = (cx.groupby("country_en")["usd_k"].sum()
           .sort_values(ascending=False).index.tolist())
    # 제목 바가 왼쪽 차트 제목과 같은 줄에 오도록 콤보박스보다 먼저 그린다
    c_sel = st.session_state.get("cx_c", "United States")
    if c_sel not in _cl:
        c_sel = _cl[0]
    sub(f"{c_sel} — 연도별 수출 (HS 구성)", "US$mn")
    c_sel = st.selectbox("국가 선택", _cl,
                         index=_cl.index(c_sel), key="cx_c")
    cc = cx[cx["country_en"] == c_sel].groupby(
        ["year", "hs"], as_index=False)["usd_k"].sum()
    cc["usd_mn"] = cc["usd_k"] / 1000
    bars2 = alt.Chart(cc).mark_bar().encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("usd_mn:Q", title="수출 (US$mn)"),
        color=alt.Color("hs:N", title=None,
                        legend=alt.Legend(orient="top", columns=2,
                                          labelLimit=220)),
        tooltip=["year:O", "hs", alt.Tooltip("usd_mn:Q", format=",.0f")])
    tot2 = cc.groupby("year", as_index=False)["usd_mn"].sum()
    txt2 = alt.Chart(tot2).mark_text(dy=-8, fontSize=11,
                                     color="#c6d0de").encode(
        x=alt.X("year:O"), y=alt.Y("usd_mn:Q"),
        text=alt.Text("usd_mn:Q", format=",.0f"))
    st.altair_chart((bars2 + txt2).properties(height=380),
                    use_container_width=True)
    st.caption("**읽는법**: 거의 모든 나라에서 3304(기초·색조)가 대부분. "
               "선케어는 HS상 분리 불가(3304 안에 포함), 마스크팩은 3307에 "
               "섞임 — 관세청 분류의 한계.")

# ---- 톱 10 국가 표
sub(f"Top 10 시장 — {_y_full}년", "YoY · 점유율")
t_now = cx[cx["year"] == _y_full].groupby(
    ["country_en", "region"], as_index=False)["usd_k"].sum()
t_prev = cx[cx["year"] == _y_full - 1].groupby(
    "country_en", as_index=False)["usd_k"].sum()
t = t_now.merge(t_prev, on="country_en", suffixes=("", "_p"), how="left")
t["usd_mn"] = t["usd_k"] / 1000
t["yoy"] = (t["usd_k"] / t["usd_k_p"] - 1) * 100
t["share"] = t["usd_k"] / t["usd_k"].sum() * 100
t = t.sort_values("usd_k", ascending=False).head(10)
view_t = t[["country_en", "region", "usd_mn", "yoy", "share"]].copy()
view_t.columns = ["국가", "권역", f"{_y_full} 수출(US$mn)", "YoY", "점유율"]
_num2 = st.column_config.NumberColumn
st.dataframe(view_t, hide_index=True, use_container_width=True,
             column_config={f"{_y_full} 수출(US$mn)": _num2(format="localized"),
                            "YoY": _num2(format="%+.0f%%"),
                            "점유율": _num2(format="%.1f%%")})

st.divider()
st.caption(f"**출처**: 관세청 수출입무역통계(tradedata.go.kr) 직접 수집 — "
           "customs_fetch.py, 월×국가×HS4·수리일 기준·공공누리 제1유형(출처 표시). "
           f"수집 {_meta.get('fetched', '—')[:10]}, 최신 확정월 "
           f"{_lm.replace('-', '.')}. 일배치에 포함돼 새 달이 공표되면 자동 반영. "
           "미매핑 국가는 권역 'Others'로 표시. 선케어 분리 불가·마스크팩 3307 "
           "포함 등 HS 한계는 kbeauty/docs/HSK_FINDINGS.md 참조.")
