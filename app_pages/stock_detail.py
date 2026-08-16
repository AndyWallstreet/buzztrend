# -*- coding: utf-8 -*-
"""종목 상세 — Butler/BigFinance 스타일 종목 페이지.

한 종목의 모든 것을 한 화면에: 밸류에이션 스냅샷, 분기 실적·마진 추이(DART),
과거 멀티플, 업종 내 위치, 최근 공시. 밸류 스크리너에서 종목을 클릭하거나
?ticker=A123456 으로 바로 진입할 수 있다.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

sys.path.append(str(Path(__file__).resolve().parent))
from history_fetch import (dart_key, load_filings, load_financials,  # noqa: E402
                           load_history)

DATA = Path(__file__).resolve().parent.parent / "data" / "screener"

st.set_page_config(page_title="종목 상세", page_icon="📋", layout="wide")

MULTIPLES = {"EV/Sales": "ev_sales", "EV/EBIT": "ev_ebit", "EV/EBITDA": "ev_ebitda",
             "EV/FCF": "ev_fcf", "PER": "per", "PBR": "pbr"}
C_BAR = "#2a78d6"
C_LINE = "#eb6834"


@st.cache_data(ttl=3600, show_spinner=False)
def load():
    df = pd.read_csv(DATA / "screener_data.csv")
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    for _c in MULTIPLES.values():
        if _c not in df.columns:
            df[_c] = np.nan
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    df["label"] = df["company"] + " (" + df["ticker"] + ")"
    return df, meta


df, meta = load()

# ---------------------------------------------------------------- 종목 선택
qs_ticker = st.query_params.get("ticker", "")
_labels = df["label"].sort_values().tolist()


def _search_stocks(q: str):
    ql = q.strip().lower()
    if not ql:
        return []
    return [s for s in _labels if ql in s.lower()][:60]


c_top1, c_top2 = st.columns([1.2, 2.8], gap="large")
with c_top1:
    picked = st_searchbox(_search_stocks, key="sd_pick",
                          label="종목 검색 (이름/티커 — 단어 포함만 표시)",
                          placeholder="예: SILICON2 또는 A257720",
                          clear_on_submit=False)

ticker = None
if picked:
    ticker = picked.rsplit("(", 1)[1].rstrip(")")
    st.query_params["ticker"] = ticker
elif qs_ticker and qs_ticker in set(df["ticker"]):
    ticker = qs_ticker

if ticker is None:
    st.title("📋 종목 상세")
    st.info("위에서 종목을 검색하거나, 밸류 스크리너의 표에서 '📋 상세' 링크를 눌러 "
            "들어올 수 있습니다.")
    st.stop()

row = df[df["ticker"] == ticker].iloc[0]
t6 = ticker.lstrip("A")

# ---------------------------------------------------------------- 헤더
with c_top2:
    st.title(f"📋 {row['company']}")
    st.caption(f"{ticker} · {row['sector']} › {row['industry_group']} › {row['industry']} · "
               f"기준일 {meta['as_of']} · "
               f"[네이버금융](https://finance.naver.com/item/main.naver?code={t6}) · "
               f"[DART](https://dart.fss.or.kr/html/search/SearchCompany_M2.html?textCrpNm={t6})")

# 밸류에이션 스냅샷 (스크리너 데이터 = 2026E 우선, 없으면 LTM)
m1, m2, m3, m4, m5, m6 = st.columns(6)
def _metric(col, name, val, fmt="{:.2f}", suffix="배", src=None):
    txt = fmt.format(val) + suffix if pd.notna(val) else "—"
    col.metric(name, txt, delta=src, delta_color="off")

_metric(m1, "시가총액", row["mcap"] / 1000 if pd.notna(row["mcap"]) else np.nan,
        "{:,.0f}", "십억원")
_metric(m2, "ROIC+SG", row["roic_sg"] * 100 if pd.notna(row["roic_sg"]) else np.nan,
        "{:.1f}", "%")
for col, lbl in [(m3, "EV/Sales"), (m4, "EV/EBIT"), (m5, "PER"), (m6, "PBR")]:
    c = MULTIPLES[lbl]
    src = row.get(f"{c}_src") if f"{c}_src" in df.columns else None
    _metric(col, lbl, row[c], src=(src if isinstance(src, str) and src else None))
st.caption("멀티플은 2026E 컨센서스 우선(작은 글씨 = 기준), 없으면 LTM. EV/FCF·PBR은 LTM/장부가.")

st.divider()

# ---------------------------------------------------------------- 분기 실적
st.markdown("#### 📊 분기 실적 (DART 연결 기준)")
if not dart_key():
    st.info("DART_API_KEY가 설정돼 있지 않아 분기 실적을 불러올 수 없습니다.")
else:
    try:
        with st.spinner("DART에서 분기 실적을 불러오는 중… (종목당 첫 조회만 10초쯤)"):
            fin, _fmeta = load_financials(t6)
        fin = fin.tail(16).copy()   # 최근 4년
        fin["매출(억)"] = fin["rev"] / 1e8
        fin["영업이익(억)"] = fin["ebit"] / 1e8
        fin["순이익(억)"] = fin["ni"] / 1e8
        fin["OPM(%)"] = np.where(fin["rev"] > 0, fin["ebit"] / fin["rev"] * 100, np.nan)
        fin["YoY(%)"] = fin["rev"].pct_change(4) * 100

        g1, g2 = st.columns([2.2, 1.8], gap="large")
        with g1:
            base = alt.Chart(fin).encode(x=alt.X("q:N", title=None, sort=None))
            bars = base.mark_bar(color=C_BAR, opacity=0.85).encode(
                y=alt.Y("매출(억):Q", title="매출 (억원)"),
                tooltip=["q", alt.Tooltip("매출(억)", format=",.0f"),
                         alt.Tooltip("영업이익(억)", format=",.0f"),
                         alt.Tooltip("OPM(%)", format=".1f")])
            line = base.mark_line(color=C_LINE, size=2.5, point=True).encode(
                y=alt.Y("OPM(%):Q", title="영업이익률 (%)"),
                tooltip=["q", alt.Tooltip("OPM(%)", format=".1f")])
            st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent")
                            .properties(height=330), use_container_width=True)
            st.caption("파란 막대 = 분기 매출, 주황 선 = 영업이익률(OPM)")
        with g2:
            t = fin.tail(8)[["q", "매출(억)", "YoY(%)", "영업이익(억)", "OPM(%)", "순이익(억)"]].copy()
            for c in t.columns[1:]:
                t[c] = t[c].round(1)
            t.columns = ["분기", "매출(억)", "YoY%", "영업이익(억)", "OPM%", "순이익(억)"]
            st.dataframe(t.iloc[::-1], hide_index=True, use_container_width=True, height=330)
    except Exception as e:
        st.warning(f"분기 실적 조회 실패: {e}")

st.divider()

# ---------------------------------------------------------------- 과거 멀티플
st.markdown("#### 📈 과거 멀티플")
h1, h2 = st.columns([1, 3.2], gap="large")
with h1:
    ciq_csv = DATA / "history_ciq" / f"{ticker}.csv"
    use_ciq = ciq_csv.exists()
    if use_ciq:
        HM = {"EV/Sales": "evs", "EV/EBIT": "eve", "EV/EBITDA": "ebitda",
              "PER": "per", "PBR": "pbr"}
    else:
        HM = {"EV/Sales": "evs", "EV/EBIT": "eve", "PER": "per", "PBR": "pbr"}
    sel_m = st.selectbox("멀티플", list(HM), index=0, key="sd_hm")
    dur = st.radio("기간", ["1년", "3년", "5년", "10년(최대)"], index=2, key="sd_dur")
    days = {"1년": 365, "3년": 365 * 3, "5년": 365 * 5, "10년(최대)": 3650}[dur]

hist = None
try:
    if use_ciq:
        hist = pd.read_csv(ciq_csv)
        hist["date"] = pd.to_datetime(hist["date"]).dt.date
        src_note = "데이터: Capital IQ (월별, LTM)"
    elif dart_key():
        with st.spinner("과거 데이터 계산 중…"):
            hist, _hm = load_history(t6)
        src_note = "데이터: 네이버 주가 + DART 재무 (주간, TTM 근사)"
    else:
        src_note = ""
except Exception as e:
    st.warning(f"과거 멀티플 조회 실패: {e}")

if hist is not None:
    hcol = HM[sel_m]
    if hcol in hist.columns:
        h = hist[hist[hcol].notna()
                 & (hist["date"] >= dt.date.today() - dt.timedelta(days=days))]
        if len(h):
            avg = float(h[hcol].mean())
            cur_col = MULTIPLES.get(sel_m)
            cur = float(row[cur_col]) if cur_col and pd.notna(row[cur_col]) else None
            line = alt.Chart(h).mark_line(color=C_BAR, size=2).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y(hcol, title=sel_m, scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("date:T", title="날짜"),
                         alt.Tooltip(hcol, title=sel_m, format=".2f")])
            layers = [line,
                      alt.Chart(pd.DataFrame({"v": [avg]})).mark_rule(
                          strokeDash=[6, 4], color="#888").encode(y="v")]
            if cur is not None:
                layers.append(alt.Chart(pd.DataFrame({"v": [cur]})).mark_rule(
                    strokeDash=[2, 3], color=C_LINE, size=2).encode(y="v"))
            with h2:
                st.altair_chart(alt.layer(*layers).properties(height=320).interactive(),
                                use_container_width=True)
            with h1:
                st.markdown(f"- 기간 평균: **{avg:.2f}배**"
                            + (f"\n- 현재(스크리너): **{cur:.2f}배**" if cur is not None else ""))
                st.caption(src_note + " · 회색 점선 = 기간 평균, 주황 점선 = 현재")
        else:
            with h2:
                st.info("이 구간에 표시할 데이터가 없습니다.")
    else:
        with h2:
            st.info(f"{sel_m} 히스토리가 없습니다.")

st.divider()

# ---------------------------------------------------------------- 업종 내 위치
st.markdown(f"#### 🏭 업종 내 위치 — {row['industry']}")
peers = df[df["industry"] == row["industry"]]
v = peers[peers["roic_sg"].notna() & peers["ev_sales"].notna()
          & (peers["ev_sales"] > 0)].copy()
if len(v) >= 3:
    v["점수"] = ((v["roic_sg"].rank(pct=True)
                 + (1 - v["ev_sales"].rank(pct=True))) / 2 * 100).round(0)
    v = v.sort_values("점수", ascending=False).reset_index(drop=True)
    my_rank = (v["ticker"] == ticker).idxmax() + 1 if (v["ticker"] == ticker).any() else None
    if my_rank:
        st.markdown(f"'좋은데 싼' 점수 기준 **{len(v)}개 중 {my_rank}위** "
                    "(질 = ROIC+SG, 가격 = EV/Sales 백분위)")
    t = v.head(10)[["company", "ticker", "점수", "roic_sg", "ev_sales", "per", "mcap"]].copy()
    t["roic_sg"] = (t["roic_sg"] * 100).round(1)
    t["ev_sales"] = t["ev_sales"].round(2)
    t["per"] = t["per"].round(1)
    t["mcap"] = (t["mcap"] / 1000).round(0)
    t.columns = ["회사", "티커", "점수", "ROIC+SG(%)", "EV/Sales", "PER", "시총(십억)"]
    st.dataframe(t, hide_index=True, use_container_width=True)
else:
    st.caption("업종 피어가 부족합니다.")

st.divider()

# ---------------------------------------------------------------- 최근 공시
st.markdown("#### 📰 최근 공시 (1년)")
if dart_key():
    filings = load_filings(t6)
    if filings:
        ft = pd.DataFrame(filings, columns=["날짜", "보고서", "링크"])
        ft["날짜"] = ft["날짜"].str.replace(r"(\d{4})(\d{2})(\d{2})", r"\1-\2-\3", regex=True)
        st.dataframe(ft, hide_index=True, use_container_width=True,
                     column_config={"링크": st.column_config.LinkColumn("DART", display_text="📄 열기")})
    else:
        st.caption("공시 조회 결과가 없습니다.")
else:
    st.caption("DART_API_KEY가 없어 공시를 불러올 수 없습니다.")

st.divider()
st.caption("데이터: 밸류에이션 = Capital IQ 기반 스크리너 데이터(2026E 우선) · "
           "분기 실적/공시 = DART OpenAPI (연결 CFS, 분기 단독 환산) · "
           "과거 멀티플 = CIQ 관심종목 또는 네이버+DART 즉석 계산. "
           "숫자는 참고용이며 원공시와 다를 수 있습니다.")
