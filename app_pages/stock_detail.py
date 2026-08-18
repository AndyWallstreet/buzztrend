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
import importlib  # noqa: E402

import history_fetch  # noqa: E402

# 배포 서버가 예전 버전 모듈을 캐시하고 있으면 새 함수가 없어 ImportError가
# 나므로, 없으면 다시 로드한다
if not hasattr(history_fetch, "load_financials"):
    history_fetch = importlib.reload(history_fetch)
dart_key = history_fetch.dart_key
load_filings = history_fetch.load_filings
load_financials = history_fetch.load_financials
load_history = history_fetch.load_history

DATA = Path(__file__).resolve().parent.parent / "data" / "screener"

st.set_page_config(page_title="종목 상세", page_icon="📋", layout="wide")

MULTIPLES = {"EV/Sales": "ev_sales", "EV/EBIT": "ev_ebit", "EV/EBITDA": "ev_ebitda",
             "EV/FCF": "ev_fcf", "PER": "per", "PBR": "pbr"}
C_BAR = "#2a78d6"
C_LINE = "#eb6834"


def _fmt_won(x):
    """원 단위 금액 -> '1.5조' / '1,234억' 표기."""
    if pd.isna(x):
        return "—"
    return f"{x / 1e12:,.1f}조" if abs(x) >= 1e12 else f"{x / 1e8:,.0f}억"


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
    """전 종목 분기 재무 DB (findb_update.py가 주기적으로 갱신). 없으면 None."""
    p = DATA.parent / "findb" / "financials.csv.gz"
    if not p.exists():
        return None
    fdb = pd.read_csv(p)
    fdb["date"] = pd.to_datetime(fdb["date"]).dt.date
    return fdb


@st.cache_data(ttl=3600, show_spinner=False)
def load_capexdb():
    """Capex(유형/무형 취득) DB (capexdb_update.py가 매일 커버리지 확장). 없으면 None."""
    p = DATA.parent / "capexdb" / "capex.csv.gz"
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(ttl=3600, show_spinner=False)
def load_histdb():
    """전 종목 과거 멀티플 DB (histdb_update.py가 주기적으로 갱신). 없으면 None."""
    p = DATA.parent / "histdb" / "multiples.csv.gz"
    if not p.exists():
        return None
    hdb = pd.read_csv(p)
    hdb["date"] = pd.to_datetime(hdb["date"]).dt.date
    return hdb


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
_fdb = load_findb()
_db_fin = None
if _fdb is not None:
    _db_fin = _fdb[_fdb["ticker"] == ticker]
    if len(_db_fin) < 4:
        _db_fin = None
if _db_fin is None and not dart_key():
    st.info("DART_API_KEY가 설정돼 있지 않아 분기 실적을 불러올 수 없습니다.")
else:
    try:
        if _db_fin is not None:
            fin = _db_fin.copy()   # DB에서 즉시 로딩
        else:
            with st.spinner("DART에서 분기 실적을 불러오는 중… (종목당 첫 조회만 10초쯤)"):
                fin, _fmeta = load_financials(t6)
        fin = fin[fin["rev"].notna()].copy()
        fin["_yr"] = fin["q"].str[:4].astype(int)

        # 주기(분기/연간) 토글 + 연도 범위 슬라이더 (끝까지 끌면 최대 = 직접설정 겸용)
        fc1, fc2 = st.columns([1, 3], gap="large")
        with fc1:
            freq = st.radio("주기", ["분기", "연간"], horizontal=True, key="sd_freq")
        with fc2:
            y_min, y_max_ = int(fin["_yr"].min()), int(fin["_yr"].max())
            if y_min < y_max_:
                y0, y1 = st.slider("기간 (연도 범위 — 끝까지 끌면 최대)",
                                   y_min, y_max_, (max(y_min, y_max_ - 3), y_max_),
                                   key="sd_finyr")
            else:
                y0 = y1 = y_min
        fin = fin[(fin["_yr"] >= y0) & (fin["_yr"] <= y1)]

        if freq == "연간":
            g = fin.groupby("_yr")
            fin = pd.DataFrame({
                "rev": g["rev"].sum(min_count=1),
                "ebit": g["ebit"].sum(min_count=1),
                "ni": g["ni"].sum(min_count=1),
                "n_q": g["rev"].count(),
            }).reset_index()
            # 분기가 4개 안 되는 해(올해 등)는 * 표시
            fin["q"] = fin["_yr"].astype(str) + np.where(fin["n_q"] < 4, "*", "")
            fin["YoY(%)"] = fin["rev"].pct_change(1) * 100
            x_title = "연간 (* = 진행 중인 해)"
        else:
            fin = fin.sort_values("date" if "date" in fin.columns else "q")
            fin["YoY(%)"] = fin["rev"].pct_change(4) * 100
            x_title = None
        fin["매출(억)"] = fin["rev"] / 1e8
        fin["영업이익(억)"] = fin["ebit"] / 1e8
        fin["순이익(억)"] = fin["ni"] / 1e8
        fin["OPM(%)"] = np.where(fin["rev"] > 0, fin["ebit"] / fin["rev"] * 100, np.nan)
        _lag = 4 if freq == "분기" else 1
        fin["매출YoY(%)"] = fin["rev"].pct_change(_lag) * 100
        # 증가율은 직전값이 0 이하(적자 등)면 의미가 없어 비움
        fin["영업YoY(%)"] = np.where(fin["ebit"].shift(_lag) > 0,
                                    fin["ebit"].pct_change(_lag) * 100, np.nan)
        fin["매출QoQ(%)"] = fin["rev"].pct_change(1) * 100
        fin["영업QoQ(%)"] = np.where(fin["ebit"].shift(1) > 0,
                                    fin["ebit"].pct_change(1) * 100, np.nan)

        def bar_line(df, bar_col, bar_title, line_col, line_title):
            base = alt.Chart(df).encode(x=alt.X("q:N", title=x_title, sort=None))
            bars = base.mark_bar(color=C_BAR, opacity=0.85).encode(
                y=alt.Y(f"{bar_col}:Q", title=bar_title),
                tooltip=["q", alt.Tooltip(bar_col, format=",.0f"),
                         alt.Tooltip(line_col, format=".1f")])
            line = base.mark_line(color=C_LINE, size=2.5, point=True).encode(
                y=alt.Y(f"{line_col}:Q", title=line_title),
                tooltip=["q", alt.Tooltip(line_col, format=".1f")])
            return (alt.layer(bars, line).resolve_scale(y="independent")
                    .properties(height=270))

        r1c1, r1c2 = st.columns(2, gap="large")
        with r1c1:
            st.markdown("**매출** · 주황 선 = 매출 증가율(YoY)")
            st.altair_chart(bar_line(fin, "매출(억)", "매출 (억원)",
                                     "매출YoY(%)", "매출 YoY (%)"),
                            use_container_width=True)
        with r1c2:
            st.markdown("**영업이익** · 주황 선 = 영업이익률(OPM)")
            st.altair_chart(bar_line(fin, "영업이익(억)", "영업이익 (억원)",
                                     "OPM(%)", "영업이익률 (%)"),
                            use_container_width=True)

        r2c1, r2c2 = st.columns(2, gap="large")
        with r2c1:
            _basis = "YoY"
            if freq == "분기":
                _basis = st.radio("증가율 기준", ["YoY", "QoQ"], horizontal=True,
                                  key="sd_lev_basis")
            st.markdown(f"**오퍼레이팅 레버리지** — 매출 vs 영업이익 증가율 ({_basis})")
            _g1, _g2 = f"매출{_basis}(%)", f"영업{_basis}(%)"
            lev = fin[["q", _g1, _g2]].melt("q", var_name="지표", value_name="증가율")
            lev_chart = alt.Chart(lev).mark_line(size=2.5, point=True).encode(
                x=alt.X("q:N", title=x_title, sort=None),
                y=alt.Y("증가율:Q", title="증가율 (%)"),
                color=alt.Color("지표:N",
                                scale=alt.Scale(domain=[_g1, _g2],
                                                range=[C_BAR, C_LINE]),
                                legend=alt.Legend(orient="top")),
                tooltip=["q", "지표", alt.Tooltip("증가율", format=".1f")])
            zero = alt.Chart(pd.DataFrame({"v": [0]})).mark_rule(
                color="#666", strokeDash=[4, 3]).encode(y="v")
            st.altair_chart(alt.layer(lev_chart, zero).properties(height=250),
                            use_container_width=True)
            st.caption("주황(영업이익)이 파랑(매출) 위에 있으면 레버리지가 작동 중 — "
                       "매출보다 이익이 빨리 늘고 있다는 뜻.")
        with r2c2:
            st.markdown("**Capex — 유형/무형자산 취득**")
            _cdb = load_capexdb()
            _cx = _cdb[_cdb["ticker"] == ticker] if _cdb is not None else None
            if _cx is not None and len(_cx) >= 2:
                cx = _cx.copy()
                cx["_yr"] = cx["q"].str[:4].astype(int)
                cx = cx[(cx["_yr"] >= y0) & (cx["_yr"] <= y1)]
                if freq == "연간":
                    gg = cx.groupby("_yr")
                    cx = pd.DataFrame({
                        "capex_t": gg["capex_t"].sum(min_count=1),
                        "capex_i": gg["capex_i"].sum(min_count=1),
                        "n_q": gg["capex_t"].count()}).reset_index()
                    cx["q"] = cx["_yr"].astype(str) + np.where(cx["n_q"] < 4, "*", "")
                cx["유형(억)"] = cx["capex_t"] / 1e8
                cx["무형(억)"] = cx["capex_i"] / 1e8
                cm = cx[["q", "유형(억)", "무형(억)"]].melt("q", var_name="구분",
                                                          value_name="capex")
                cap_chart = alt.Chart(cm).mark_bar(opacity=0.9).encode(
                    x=alt.X("q:N", title=x_title, sort=None),
                    y=alt.Y("capex:Q", title="Capex (억원)", stack=True),
                    color=alt.Color("구분:N",
                                    scale=alt.Scale(domain=["유형(억)", "무형(억)"],
                                                    range=[C_BAR, "#8ec9ff"]),
                                    legend=alt.Legend(orient="top")),
                    tooltip=["q", "구분", alt.Tooltip("capex", format=",.0f")])
                st.altair_chart(cap_chart.properties(height=250),
                                use_container_width=True)
                st.caption("현금흐름표 기준 취득액 (분기 단독 환산) · 2021년 이후")
            else:
                st.info("이 종목의 Capex는 아직 수집 전입니다 — 관심종목·시총 상위부터 "
                        "매일 조금씩 수집이 넓어집니다 (capexdb_update.py).")

        t = fin.tail(12)[["q", "매출(억)", "매출YoY(%)", "영업이익(억)", "영업YoY(%)",
                          "OPM(%)", "순이익(억)"]].copy()
        for c in t.columns[1:]:
            t[c] = t[c].round(1)
        t.columns = [("분기" if freq == "분기" else "연도"), "매출(억)", "매출YoY%",
                     "영업이익(억)", "영업YoY%", "OPM%", "순이익(억)"]
        st.dataframe(t.iloc[::-1], hide_index=True, use_container_width=True,
                     height=min(80 + 36 * len(t), 380))
    except Exception as e:
        st.warning(f"분기 실적 조회 실패 ({type(e).__name__})")

st.divider()

# ---------------------------------------------------------------- 퀄리티 체크
# 사용자 워크플로 ①: "이 사업이 좋은 사업인가" — ROIC·현금창출·운전자본·주주환원
st.markdown("#### 🧭 퀄리티 체크 — ROIC · 현금흐름 · 주주환원")

_cdb2 = load_capexdb()
qd = None
if _fdb is not None and _cdb2 is not None:
    _fq = _fdb[_fdb["ticker"] == ticker].copy()
    _cq = _cdb2[_cdb2["ticker"] == ticker].copy()
    if len(_fq) >= 4 and len(_cq) and "cash" in _cq.columns \
            and _cq["cash"].notna().any():
        qd = _fq.merge(_cq.drop(columns=["date"], errors="ignore"),
                       on=["ticker", "q"], how="left").sort_values("q")

if qd is None:
    st.info("이 종목의 상세 재무(현금·부채·CFO·운전자본)는 아직 수집 전입니다 — "
            "관심종목·시총 상위부터 매일 자동으로 수집이 넓어집니다.")
else:
    for _c in ["capex_t", "capex_i", "cfo", "dep", "div_paid", "buyback", "cogs",
               "sga", "cash", "stfin", "ar", "inv", "ap", "debt", "lease"]:
        if _c not in qd.columns:
            qd[_c] = np.nan
    # TTM 합계 (분기 4개 롤링)
    for _c in ["rev", "ebit", "ni", "cfo", "cogs"]:
        qd[f"{_c}_ttm"] = qd[_c].rolling(4, min_periods=4).sum()
    qd["capex"] = qd["capex_t"].fillna(0) + qd["capex_i"].fillna(0)
    qd["capex_ttm"] = qd["capex"].rolling(4, min_periods=4).sum()

    # ROIC = NOPAT(TTM, 세율 25% 가정) / 투하자본(자본 + 차입 - 현금성)
    _z = lambda c: qd[c].fillna(0)
    qd["ic"] = np.where(qd["cash"].notna(),
                        qd["eq"] + _z("debt") + _z("lease")
                        - _z("cash") - _z("stfin"), np.nan)
    qd["ROIC(%)"] = np.where(qd["ic"] > 0,
                             qd["ebit_ttm"] * 0.75 / qd["ic"] * 100, np.nan)
    qd["netdebt"] = np.where(qd["cash"].notna(),
                             _z("debt") + _z("lease") - _z("cash") - _z("stfin"),
                             np.nan)
    # 현금창출력
    # 극단값은 ±300%로 잘라 차트가 눌리는 것을 방지
    qd["CFO/EBIT(%)"] = np.where(qd["ebit_ttm"] > 0,
                                 (qd["cfo_ttm"] / qd["ebit_ttm"] * 100)
                                 .clip(-300, 300), np.nan)
    qd["fcf_ttm"] = qd["cfo_ttm"] - qd["capex_ttm"]
    qd["FCF/순이익(%)"] = np.where(qd["ni_ttm"] > 0,
                                  (qd["fcf_ttm"] / qd["ni_ttm"] * 100)
                                  .clip(-300, 300), np.nan)
    # 운전자본 일수 (재고·매입은 매출원가 기준, 없으면 매출 기준)
    _base = np.where(qd["cogs_ttm"] > 0, qd["cogs_ttm"], qd["rev_ttm"])
    qd["매출채권일수"] = np.where(qd["rev_ttm"] > 0, qd["ar"] / qd["rev_ttm"] * 365, np.nan)
    qd["재고일수"] = np.where(_base > 0, qd["inv"] / _base * 365, np.nan)
    qd["매입채무일수"] = np.where(_base > 0, qd["ap"] / _base * 365, np.nan)
    qd["CCC일수"] = qd["매출채권일수"] + qd["재고일수"] - qd["매입채무일수"]

    qv = qd[qd["ROIC(%)"].notna() | qd["CFO/EBIT(%)"].notna()]
    _last = qd.dropna(subset=["netdebt"]).tail(1)
    _nd = float(_last["netdebt"].iloc[0]) if len(_last) else np.nan

    # 한 줄 요약 (애널리스트 첫인상)
    _bits = []
    _r = qv["ROIC(%)"].dropna()
    if len(_r):
        _bits.append(f"ROIC 최근 **{_r.iloc[-1]:.1f}%** (3년 평균 {_r.tail(12).mean():.1f}%)")
    _cc = qv["CFO/EBIT(%)"].dropna()
    if len(_cc):
        _bits.append(f"CFO/EBIT **{_cc.iloc[-1]:.0f}%**")
    if pd.notna(_nd):
        _bits.append(("순현금 **" + _fmt_won(-_nd) + "**") if _nd < 0
                     else ("순부채 **" + _fmt_won(_nd) + "**"))
    if _bits:
        st.markdown("· ".join(_bits))

    def _line_chart(data, cols, colors, y_title, pct=True, height=250):
        dd = data[["q"] + cols].melt("q", var_name="지표", value_name="v")
        dd = dd[dd["v"].notna()]
        if not len(dd):
            return None
        ch = alt.Chart(dd).mark_line(size=2.2, point=True).encode(
            x=alt.X("q:N", title=None, sort="ascending",
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("v:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color("지표:N", scale=alt.Scale(domain=cols, range=colors),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["q", "지표", alt.Tooltip("v", format=".1f")])
        zero = alt.Chart(pd.DataFrame({"v": [0]})).mark_rule(
            color="#999", strokeDash=[4, 3]).encode(y="v")
        return alt.layer(ch, zero).properties(height=height)

    qc1, qc2 = st.columns(2, gap="large")
    with qc1:
        st.markdown("**ROIC (TTM, 세율 25% 가정)** — 자본을 얼마나 잘 굴리는가")
        ch = _line_chart(qv, ["ROIC(%)"], [C_BAR], "ROIC (%)")
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
        else:
            st.info("투하자본 계산에 필요한 데이터가 부족합니다.")
    with qc2:
        st.markdown("**현금창출력 (TTM)** — 이익이 실제 현금으로 들어오는가")
        ch = _line_chart(qv, ["CFO/EBIT(%)", "FCF/순이익(%)"], [C_BAR, C_LINE], "%")
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
            st.caption("CFO/EBIT 100% 내외면 이익의 질이 좋음. FCF/순이익이 낮으면 "
                       "Capex·운전자본이 이익을 먹고 있다는 뜻.")
        else:
            st.info("현금흐름 데이터가 부족합니다.")

    qc3, qc4 = st.columns(2, gap="large")
    with qc3:
        st.markdown("**운전자본 일수** — 돈이 얼마나 묶이는가 (CCC = 채권+재고−채무)")
        _ccc_cols = [c for c in ["매출채권일수", "재고일수", "매입채무일수", "CCC일수"]
                     if qv[c].notna().any()]
        ch = _line_chart(qv, _ccc_cols,
                         ["#8ec9ff", "#f2b06c", "#b5b5b5", C_LINE][:len(_ccc_cols)],
                         "일수")
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
        else:
            st.info("운전자본 데이터가 부족합니다.")
    with qc4:
        st.markdown("**주주환원 (연간)** — 배당 + 자사주, 선 = 환원율(순이익 대비)")
        ya = qd.copy()
        ya["_yr"] = ya["q"].str[:4]
        g = ya.groupby("_yr")
        yr = pd.DataFrame({
            "배당(억)": g["div_paid"].sum(min_count=1) / 1e8,
            "자사주(억)": g["buyback"].sum(min_count=1) / 1e8,
            "ni": g["ni"].sum(min_count=1),
            "n_q": g["rev"].count()}).reset_index()
        yr = yr[(yr["n_q"] >= 4)
                & yr[["배당(억)", "자사주(억)"]].notna().any(axis=1)]
        yr["환원율(%)"] = np.where(
            yr["ni"] > 0,
            (yr["배당(억)"].fillna(0) + yr["자사주(억)"].fillna(0)) * 1e8
            / yr["ni"] * 100, np.nan)
        if len(yr) and (yr["배당(억)"].notna().any() or yr["자사주(억)"].notna().any()):
            pm = yr.melt("_yr", value_vars=["배당(억)", "자사주(억)"],
                         var_name="구분", value_name="v")
            bars = alt.Chart(pm).mark_bar(opacity=0.9).encode(
                x=alt.X("_yr:N", title=None),
                y=alt.Y("v:Q", title="주주환원 (억원)", stack=True),
                color=alt.Color("구분:N",
                                scale=alt.Scale(domain=["배당(억)", "자사주(억)"],
                                                range=[C_BAR, "#8ec9ff"]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["_yr", "구분", alt.Tooltip("v", format=",.0f")])
            line = alt.Chart(yr).mark_line(color=C_LINE, size=2.5, point=True).encode(
                x="_yr:N", y=alt.Y("환원율(%):Q", title="환원율 (%)"),
                tooltip=["_yr", alt.Tooltip("환원율(%)", format=".1f")])
            st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent")
                            .properties(height=250), use_container_width=True)
        else:
            st.info("배당·자사주 데이터가 아직 없습니다 (현금흐름표 기준).")
    st.caption("데이터: DART 전체 재무제표 (2021년 이후, 분기 단독 환산). "
               "일부 계정은 회사가 주석에만 공시하면 비어 있을 수 있습니다.")

st.divider()

# ---------------------------------------------------------------- Quick DCF
# 사용자 워크플로 ②: 절대 밸류에이션 — "성장 0이어도 싼가? 시총을 정당화하려면
# 어떤 성장/OPM이 필요한가?"
st.markdown("#### 💰 Quick DCF — 절대 밸류에이션")

_mcap_won = float(row["mcap"]) * 1e6 if pd.notna(row["mcap"]) else np.nan
_dcf_base = None
if _fdb is not None:
    _fq2 = _fdb[_fdb["ticker"] == ticker].sort_values("q")
    if len(_fq2) >= 4:
        _rev_ttm = _fq2["rev"].tail(4).sum()
        _ebit_ttm = _fq2["ebit"].tail(4).sum()
        _rev_prev = _fq2["rev"].iloc[-8:-4].sum() if len(_fq2) >= 8 else np.nan
        if _rev_ttm > 0:
            _dcf_base = {"rev": _rev_ttm, "ebit": _ebit_ttm,
                         "opm": _ebit_ttm / _rev_ttm,
                         "g_ttm": (_rev_ttm / _rev_prev - 1)
                         if pd.notna(_rev_prev) and _rev_prev > 0 else np.nan}

if _dcf_base is None or pd.isna(_mcap_won):
    st.info("Quick DCF에 필요한 분기 재무 또는 시가총액 데이터가 부족합니다.")
else:
    # 과거 데이터에서 기본 가정 뽑기 (없으면 보수적 기본값)
    _capex_pct_d, _nwc_pct_d, _nd = 0.04, 0.10, 0.0
    if qd is not None:
        _cp = (qd["capex_ttm"] / qd["rev_ttm"]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(_cp):
            _capex_pct_d = float(np.clip(_cp.tail(8).median(), 0.0, 0.30))
        _nw = ((qd["ar"].fillna(0) + qd["inv"].fillna(0) - qd["ap"].fillna(0))
               / qd["rev_ttm"]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(_nw):
            _nwc_pct_d = float(np.clip(_nw.tail(8).median(), 0.0, 0.50))
        _ndl = qd.dropna(subset=["netdebt"]).tail(1)
        if len(_ndl):
            _nd = float(_ndl["netdebt"].iloc[0])

    dc1, dc2 = st.columns([1.15, 2.85], gap="large")
    with dc1:
        st.markdown("**가정 입력**")
        _g_def = 10
        if pd.notna(_dcf_base["g_ttm"]):
            _g_def = int(np.clip(round(_dcf_base["g_ttm"] * 100), 0, 30))
        g5 = st.slider("매출 성장률 — 향후 5년 (연 %)", -20, 50, _g_def, key="dcf_g")
        opm_in = st.slider("영업이익률 OPM (%)", 0.0, 50.0,
                           float(np.clip(round(_dcf_base["opm"] * 100, 1), 0.0, 50.0)),
                           0.5, key="dcf_opm")
        wacc_in = st.slider("할인율 WACC (%)", 6.0, 15.0, 10.0, 0.5, key="dcf_wacc")
        with st.expander("세부 가정"):
            gt_in = st.slider("영구 성장률 (%)", 0.0, 3.0, 1.5, 0.5, key="dcf_gt")
            tax_in = st.slider("세율 (%)", 15, 30, 25, key="dcf_tax")
            capex_in = st.slider("Capex (매출 대비 %)", 0.0, 30.0,
                                 round(_capex_pct_d * 100, 1), 0.5, key="dcf_cx")
            dep_in = st.slider("감가상각 D&A (매출 대비 %)", 0.0, 30.0,
                               round(_capex_pct_d * 100, 1), 0.5, key="dcf_dep")
            nwc_in = st.slider("운전자본 (매출 증가분 대비 %)", 0.0, 50.0,
                               round(_nwc_pct_d * 100, 1), key="dcf_nwc")
        st.caption("기본값 = 최근 실적(TTM)과 과거 Capex·운전자본 비율에서 자동 산출. "
                   "세율 25%, WACC 10%, 영구성장 1.5%는 템플릿 기본값.")

    def dcf_equity(g, opm, wacc, gt, tax, cxp, dpp, nwp, rev0, netdebt):
        """5년 예측 + 영구가치 -> (지분가치, FCF 리스트, 터미널가치)."""
        if wacc <= gt:
            return np.nan, [], np.nan
        rev_p, fcfs = rev0, []
        for _ in range(5):
            rev_n = rev_p * (1 + g)
            nopat = rev_n * opm * (1 - tax)
            fcf = nopat + rev_n * dpp - rev_n * cxp - (rev_n - rev_p) * nwp
            fcfs.append(fcf)
            rev_p = rev_n
        tv = fcfs[-1] * (1 + gt) / (wacc - gt)
        ev = sum(f / (1 + wacc) ** (i + 1) for i, f in enumerate(fcfs))
        ev += tv / (1 + wacc) ** 5
        return ev - netdebt, fcfs, tv

    _args = dict(opm=opm_in / 100, wacc=wacc_in / 100, gt=gt_in / 100,
                 tax=tax_in / 100, cxp=capex_in / 100, dpp=dep_in / 100,
                 nwp=nwc_in / 100, rev0=_dcf_base["rev"], netdebt=_nd)
    eqv, fcfs, tv = dcf_equity(g5 / 100, **_args)

    def _irr(cfs):
        lo, hi = -0.5, 1.5
        f = lambda r: sum(c / (1 + r) ** i for i, c in enumerate(cfs))
        if f(lo) < 0 or f(hi) > 0:
            return np.nan
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    with dc2:
        if pd.isna(eqv):
            st.warning("WACC가 영구 성장률보다 커야 합니다.")
        else:
            upside = eqv / _mcap_won - 1
            irr = _irr([-_mcap_won] + fcfs[:-1] + [fcfs[-1] + tv - _nd])
            fcf0 = (_dcf_base["ebit"] * (1 - tax_in / 100)
                    + _dcf_base["rev"] * (dep_in - capex_in) / 100)
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("적정 시총 (이 가정)", _fmt_won(eqv))
            o2.metric("업사이드", f"{upside * 100:+.0f}%")
            o3.metric("기대 IRR (5년)", f"{irr * 100:.1f}%" if pd.notna(irr) else "—")
            _ev_cur = _mcap_won + _nd
            o4.metric("현재 FCF 수익률", f"{fcf0 / _ev_cur * 100:.1f}%"
                      if _ev_cur > 0 and fcf0 > 0 else "—",
                      delta="FCF(TTM기준)/현재EV", delta_color="off")

            # ---- 퀵 체크 ①: 성장 0%여도 싼가
            eq0, _, _ = dcf_equity(0.0, **{**_args, "gt": 0.0})
            if pd.notna(eq0):
                up0 = eq0 / _mcap_won - 1
                if up0 >= 0:
                    st.success(f"**성장 0% 체크** — 매출이 더 이상 안 늘어도 적정 시총 "
                               f"{_fmt_won(eq0)} → 현재보다 **{up0 * 100:+.0f}%**. "
                               "성장 없이도 싼 구간입니다.")
                else:
                    st.warning(f"**성장 0% 체크** — 성장이 멈추면 적정 시총 {_fmt_won(eq0)} "
                               f"({up0 * 100:+.0f}%). 현재 가격에는 성장 기대가 "
                               "들어가 있습니다.")

            # ---- 퀵 체크 ②: 시총을 정당화하는 성장률/OPM 역산
            def _solve(fn, lo, hi):
                if (fn(lo) - _mcap_won) * (fn(hi) - _mcap_won) > 0:
                    return np.nan
                for _ in range(60):
                    mid = (lo + hi) / 2
                    if fn(mid) < _mcap_won:
                        lo = mid
                    else:
                        hi = mid
                return (lo + hi) / 2

            _args_no_opm = {k: v for k, v in _args.items() if k != "opm"}
            g_imp = _solve(lambda g: dcf_equity(g, **_args)[0], -0.30, 0.60)
            opm_imp = _solve(lambda m: dcf_equity(0.0, opm=m, **_args_no_opm)[0],
                             0.001, 0.60)
            _msg = []
            if pd.notna(g_imp):
                _msg.append(f"OPM {opm_in:.1f}% 유지 시 **매출 연 {g_imp * 100:+.1f}% "
                            f"× 5년**")
            if pd.notna(opm_imp):
                _msg.append(f"성장 0% 가정 시 **OPM {opm_imp * 100:.1f}%**")
            if _msg:
                st.info("**현재 시총이 정당화되려면**: " + " 또는 ".join(_msg)
                        + " 정도가 필요합니다. 회사가 이걸 해낼 수 있을지가 투자 판단의 "
                          "핵심 질문.")

            # FCF 경로 미니 차트
            fdf = pd.DataFrame({"연차": [f"{i + 1}년" for i in range(5)],
                                "FCF(억)": [f / 1e8 for f in fcfs]})
            fchart = alt.Chart(fdf).mark_bar(color=C_BAR, opacity=0.85).encode(
                x=alt.X("연차:N", sort=None, title=None),
                y=alt.Y("FCF(억):Q", title="예상 FCF (억원)"),
                tooltip=["연차", alt.Tooltip("FCF(억)", format=",.0f")])
            st.altair_chart(fchart.properties(height=170), use_container_width=True)
            _nd_txt = ("순현금 " + _fmt_won(-_nd)) if _nd < 0 else ("순부채 " + _fmt_won(_nd))
            st.caption(f"5년 명시 예측 + 영구가치(그로잉 퍼페추이티) − 순부채. "
                       f"현재 시총 {_fmt_won(_mcap_won)} · {_nd_txt}"
                       + (" (상세 재무 수집 전이라 순부채 0으로 가정)" if qd is None else "")
                       + " · 참고용 간이 모델입니다.")

st.divider()

# ---------------------------------------------------------------- 과거 멀티플
# 사용자 워크플로 ③: 상대 밸류에이션 — 지금 멀티플이 과거 밴드의 어디쯤인가
st.markdown("#### 📈 과거 멀티플 밴드 — 상대 밸류에이션")
h1, h2 = st.columns([1, 3.2], gap="large")
with h1:
    ciq_csv = DATA / "history_ciq" / f"{ticker}.csv"
    use_ciq = ciq_csv.exists()
    _hdb = load_histdb()
    _hd = None
    if not use_ciq and _hdb is not None:
        _hd = _hdb[_hdb["ticker"] == ticker]
        if len(_hd) < 6:
            _hd = None
    if use_ciq:
        HM = {"EV/Sales": "evs", "EV/EBIT": "eve", "EV/EBITDA": "ebitda",
              "PER": "per", "PBR": "pbr"}
    else:
        HM = {"EV/Sales": "evs", "EV/EBIT": "eve", "PER": "per", "PBR": "pbr"}
    sel_m = st.selectbox("멀티플", list(HM), index=0, key="sd_hm")
    dur = st.radio("기간", ["1년", "3년", "5년", "10년(최대)"], index=2, key="sd_dur")
    days = {"1년": 365, "3년": 365 * 3, "5년": 365 * 5, "10년(최대)": 3650}[dur]

hist = None
src_note = ""
try:
    if use_ciq:
        hist = pd.read_csv(ciq_csv)
        hist["date"] = pd.to_datetime(hist["date"]).dt.date
        src_note = "데이터: Capital IQ (월별, LTM)"
    elif _hd is not None:
        hist = _hd    # 전 종목 사전 계산 DB — 즉시 로딩
        src_note = "데이터: 사전 계산 DB (월별, TTM — histdb_update.py로 갱신)"
    elif dart_key():
        with st.spinner("과거 데이터 계산 중…"):
            hist, _hm = load_history(t6)
        src_note = "데이터: 네이버 주가 + DART 재무 (주간, TTM 근사)"
    else:
        with h2:
            st.info("이 종목은 사전 계산 데이터가 없고, 즉석 계산용 DART 접근도 "
                    "불가한 환경입니다.")
except Exception as e:
    with h2:
        # 예외 문자열에 API 키가 섞일 수 있으므로 원문은 표시하지 않는다
        if "opendart" in str(e) or "timed out" in str(e).lower():
            st.info("서버에서 DART에 접속할 수 없어 즉석 계산이 불가합니다 "
                    "(해외 서버 차단). 사전 계산된 종목만 표시됩니다.")
        else:
            st.warning(f"과거 멀티플 조회 실패 ({type(e).__name__})")

if hist is not None:
    hcol = HM[sel_m]
    if hcol in hist.columns:
        h = hist[hist[hcol].notna()
                 & (hist["date"] >= dt.date.today() - dt.timedelta(days=days))]
        if len(h):
            avg = float(h[hcol].mean())
            q25, q75 = (float(h[hcol].quantile(x)) for x in (0.25, 0.75))
            cur_col = MULTIPLES.get(sel_m)
            cur = float(row[cur_col]) if cur_col and pd.notna(row[cur_col]) else None
            band = alt.Chart(pd.DataFrame({"y": [q25], "y2": [q75]})).mark_rect(
                opacity=0.10, color=C_BAR).encode(y="y", y2="y2")
            line = alt.Chart(h).mark_line(color=C_BAR, size=2).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y(hcol, title=sel_m, scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("date:T", title="날짜"),
                         alt.Tooltip(hcol, title=sel_m, format=".2f")])
            layers = [band, line,
                      alt.Chart(pd.DataFrame({"v": [avg]})).mark_rule(
                          strokeDash=[6, 4], color="#888").encode(y="v")]
            if cur is not None:
                layers.append(alt.Chart(pd.DataFrame({"v": [cur]})).mark_rule(
                    strokeDash=[2, 3], color=C_LINE, size=2).encode(y="v"))
            with h2:
                st.altair_chart(alt.layer(*layers).properties(height=320).interactive(),
                                use_container_width=True)
            with h1:
                _lines = [f"- 기간 평균: **{avg:.2f}배**",
                          f"- 25~75% 밴드: **{q25:.2f} ~ {q75:.2f}배**"]
                if cur is not None:
                    pctl = float((h[hcol] < cur).mean() * 100)
                    if pctl <= 25:
                        _tag = "🟢 밴드 하단 — 역사적으로 싼 구간"
                    elif pctl >= 75:
                        _tag = "🔴 밴드 상단 — 역사적으로 비싼 구간"
                    else:
                        _tag = "🟡 밴드 중간"
                    _lines.append(f"- 현재: **{cur:.2f}배** = 구간 하위 **{pctl:.0f}%**")
                    _lines.append(f"- {_tag}")
                st.markdown("\n".join(_lines))
                st.caption(src_note + " · 음영 = 25~75% 밴드, 회색 점선 = 평균, "
                           "주황 점선 = 현재")

            # 전 멀티플 위치 요약 — "PBR은 바닥, EV/Sales는 중간" 한눈에
            _rows = []
            for _lbl, _hc in HM.items():
                if _hc not in hist.columns:
                    continue
                _hs = hist[hist[_hc].notna()
                           & (hist["date"] >= dt.date.today()
                              - dt.timedelta(days=days))][_hc]
                _cc2 = MULTIPLES.get(_lbl)
                _cv = float(row[_cc2]) if _cc2 and pd.notna(row[_cc2]) else np.nan
                if len(_hs) < 6 or pd.isna(_cv):
                    continue
                _p = float((_hs < _cv).mean() * 100)
                _rows.append({"멀티플": _lbl, "현재": round(_cv, 2),
                              "기간 평균": round(float(_hs.mean()), 2),
                              "위치(하위 %)": round(_p),
                              "판정": ("🟢 싼 편" if _p <= 25 else
                                      "🔴 비싼 편" if _p >= 75 else "🟡 중간")})
            if len(_rows) >= 2:
                with h2:
                    st.dataframe(pd.DataFrame(_rows), hide_index=True,
                                 use_container_width=True)
                    st.caption("현재 멀티플(2026E 우선)을 같은 기간 히스토리와 비교한 위치. "
                               "0%에 가까울수록 역사적 저점 부근.")
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
    try:
        filings = load_filings(t6)
    except Exception:
        filings = []
    if filings:
        ft = pd.DataFrame(filings, columns=["날짜", "보고서", "링크"])
        ft["날짜"] = ft["날짜"].str.replace(r"(\d{4})(\d{2})(\d{2})", r"\1-\2-\3", regex=True)
        st.dataframe(ft, hide_index=True, use_container_width=True,
                     column_config={"링크": st.column_config.LinkColumn("DART", display_text="📄 열기")})
    else:
        st.caption(f"공시를 불러올 수 없습니다 — "
                   f"[DART에서 직접 보기](https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm={t6})")
else:
    st.caption("DART_API_KEY가 없어 공시를 불러올 수 없습니다.")

st.divider()
st.caption("데이터: 밸류에이션 = Capital IQ 기반 스크리너 데이터(2026E 우선) · "
           "분기 실적/공시 = DART OpenAPI (연결 CFS, 분기 단독 환산) · "
           "과거 멀티플 = CIQ 관심종목 또는 네이버+DART 즉석 계산. "
           "숫자는 참고용이며 원공시와 다를 수 있습니다.")
