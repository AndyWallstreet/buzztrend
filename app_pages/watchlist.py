# -*- coding: utf-8 -*-
"""Watchlist — 관심종목 대시보드 (LK Terminal 3단계).

지켜보는 종목들을 한 화면에서: 현재 밸류에이션(2026E 우선), 최근 분기
매출 YoY·영업이익률, 매출 스파크라인, 업종 내 점수, 최신 공시 모음.
목록은 data/screener/history_ciq/watchlist.txt (CIQ 히스토리 관심종목과 공유).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

sys.path.append(str(Path(__file__).resolve().parent))
import history_fetch  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "screener"
WATCH = DATA / "history_ciq" / "watchlist.txt"

st.set_page_config(page_title="Watchlist", page_icon="⭐", layout="wide")

MULTIPLES = {"EV/Sales": "ev_sales", "EV/EBIT": "ev_ebit", "EV/EBITDA": "ev_ebitda",
             "EV/FCF": "ev_fcf", "PER": "per", "PBR": "pbr"}


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


@st.cache_data(ttl=3600, show_spinner=False)
def load_findb():
    p = DATA.parent / "findb" / "financials.csv.gz"
    if not p.exists():
        return None
    return pd.read_csv(p)


df, meta = load()
fdb = load_findb()

st.title("⭐ Watchlist")
st.caption(f"기준일 {meta['as_of']} · 목록은 `watchlist.txt` 기준 "
           "(여기서 추가한 종목은 이 세션에서만 보입니다 — 영구 추가는 파일에 한 줄 추가)")

# ---------------------------------------------------------------- 목록 구성
base_list = []
if WATCH.exists():
    base_list = [t.strip().upper() for t in WATCH.read_text(encoding="utf-8").split()
                 if t.strip()]
extra = st.session_state.setdefault("wl_extra", [])

_labels = df["label"].sort_values().tolist()


def _search_stocks(q: str):
    ql = q.strip().lower()
    if not ql:
        return []
    return [s for s in _labels if ql in s.lower()][:60]


c1, c2 = st.columns([1.2, 2.8], gap="large")
with c1:
    add = st_searchbox(_search_stocks, key="wl_add",
                       label="종목 추가 (이 세션에서만)",
                       placeholder="예: SILICON2 또는 A257720",
                       clear_on_submit=True)
    if add:
        t = add.rsplit("(", 1)[1].rstrip(")")
        if t not in base_list and t not in extra:
            extra.append(t)

tickers = [t for t in base_list + extra if (df["ticker"] == t).any()]
if not tickers:
    st.info("관심종목이 없습니다. 위에서 추가하거나 watchlist.txt에 티커를 넣어주세요.")
    st.stop()

# ---------------------------------------------------------------- 표 데이터
rows = []
for t in tickers:
    r = df[df["ticker"] == t].iloc[0]
    rec = {"회사": r["company"], "티커": t,
           "시총(십억)": round(r["mcap"] / 1000) if pd.notna(r["mcap"]) else None,
           "ROIC+SG(%)": round(r["roic_sg"] * 100, 1) if pd.notna(r["roic_sg"]) else None,
           "EV/Sales": round(r["ev_sales"], 2) if pd.notna(r["ev_sales"]) else None,
           "PER": round(r["per"], 1) if pd.notna(r["per"]) else None,
           "PBR": round(r["pbr"], 2) if pd.notna(r["pbr"]) else None}
    # 업종 내 '좋은데 싼' 점수
    peers = df[df["industry"] == r["industry"]]
    v = peers[peers["roic_sg"].notna() & peers["ev_sales"].notna() & (peers["ev_sales"] > 0)]
    if len(v) >= 3 and t in set(v["ticker"]):
        sc = ((v["roic_sg"].rank(pct=True) + (1 - v["ev_sales"].rank(pct=True))) / 2 * 100)
        rec["점수"] = round(float(sc[v["ticker"] == t].iloc[0]))
    else:
        rec["점수"] = None
    # findb: 최근 분기 YoY / OPM / 매출 스파크라인
    rec["매출YoY(%)"] = rec["OPM(%)"] = None
    rec["매출 추이"] = None
    if fdb is not None:
        f = fdb[fdb["ticker"] == t].sort_values("q")
        f = f[f["rev"].notna()]
        if len(f) >= 5:
            last = f.iloc[-1]
            prev_q = f"{int(last['q'][:4]) - 1}{last['q'][4:]}"
            prev = f[f["q"] == prev_q]
            if len(prev) and prev.iloc[0]["rev"]:
                rec["매출YoY(%)"] = round((last["rev"] / prev.iloc[0]["rev"] - 1) * 100, 1)
            if last["rev"] and pd.notna(last["ebit"]):
                rec["OPM(%)"] = round(last["ebit"] / last["rev"] * 100, 1)
            rec["최근분기"] = last["q"]
            rec["매출 추이"] = (f["rev"].tail(8) / 1e8).round(0).tolist()
    rec["상세"] = f"/종목상세?ticker={t}"
    rec["네이버"] = f"https://finance.naver.com/item/main.naver?code={t.lstrip('A')}"
    rows.append(rec)

wt = pd.DataFrame(rows)
cols = ["회사", "티커", "시총(십억)", "ROIC+SG(%)", "EV/Sales", "PER", "PBR", "점수",
        "최근분기", "매출YoY(%)", "OPM(%)", "매출 추이", "상세", "네이버"]
wt = wt[[c for c in cols if c in wt.columns]]
st.dataframe(
    wt, hide_index=True, use_container_width=True,
    height=min(80 + 36 * len(wt), 520),
    column_config={
        "매출 추이": st.column_config.LineChartColumn("매출 추이 (8분기, 억원)"),
        "상세": st.column_config.LinkColumn("상세", display_text="📋"),
        "네이버": st.column_config.LinkColumn("네이버", display_text="📈"),
    })
st.caption("밸류에이션은 2026E 컨센서스 우선(없으면 LTM) · 최근분기/YoY/OPM은 DART findb 기준 · "
           "점수 = 같은 Industry 안 '좋은데 싼' 백분위(100점 만점)")

st.divider()

# ---------------------------------------------------------------- 최신 공시 모음
st.markdown("#### 📰 관심종목 최신 공시")
if not history_fetch.dart_key():
    st.caption("DART_API_KEY가 없어 공시를 불러올 수 없습니다.")
else:
    all_f = []
    with st.spinner("공시 확인 중…"):
        for t in tickers[:20]:
            name = df.loc[df["ticker"] == t, "company"].iloc[0]
            try:
                for d, nm, url in history_fetch.load_filings(t.lstrip("A"), count=5):
                    all_f.append({"날짜": d, "회사": name, "보고서": nm, "링크": url})
            except Exception:
                continue
    if all_f:
        ft = pd.DataFrame(all_f).sort_values("날짜", ascending=False).head(30)
        ft["날짜"] = ft["날짜"].str.replace(r"(\d{4})(\d{2})(\d{2})", r"\1-\2-\3", regex=True)
        st.dataframe(ft, hide_index=True, use_container_width=True,
                     column_config={"링크": st.column_config.LinkColumn(
                         "DART", display_text="📄 열기")})
    else:
        st.caption("공시 조회 결과가 없습니다.")
