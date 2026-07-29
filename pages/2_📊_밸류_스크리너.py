# -*- coding: utf-8 -*-
"""밸류 스크리너 — 싸고 좋은 주식 찾기 (Cheap & High-Quality).

Data comes from data/screener/screener_data.csv, extracted from the
Capital IQ comparables workbook (Data sheet, CW:DJ block).

Two tools, same idea as the Excel file:
  1) 티커 조회  — pick one company, see it against its peer group
  2) 조건 검색  — filter the whole market by sector + thresholds
X axis = quality (ROIC+SG or ROE+SG), Y axis = price (a multiple).
Bottom-right = high quality but cheap = worth a deeper look.
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "screener"

st.set_page_config(page_title="밸류 스크리너", page_icon="📊", layout="wide")

# ---------------------------------------------------------------- constants
MULTIPLES = {  # label -> column
    "EV/Sales": "ev_sales",
    "EV/EBIT": "ev_ebit",
    "EV/EBITDA": "ev_ebitda",
    "PER": "per",
    "PBR": "pbr",
}
X_AXES = {"ROIC+SG": "roic_sg", "ROE+SG": "roe_sg"}
CLASS_LEVELS = {  # label -> column
    "Industry Sector": "sector",
    "Industry Group": "industry_group",
    "Industry": "industry",
    "Primary Industry": "primary_industry",
    "Primary SIC Industry": "sic_industry",
}
# 멀티플별 기본 상한 (엑셀 F열 기본값과 동일)
DEFAULT_Y_MAX = {"EV/Sales": 2.0, "EV/EBIT": 15.0, "EV/EBITDA": 20.0, "PER": 20.0, "PBR": 2.0}

C_PEER = "#9ab6d8"     # 회색-파랑: 나머지 종목
C_MATCH = "#2a78d6"    # 파랑: 조건 통과 종목
C_PICK = "#eb6834"     # 주황: 선택한 종목


@st.cache_data(ttl=3600, show_spinner=False)
def load():
    df = pd.read_csv(DATA / "screener_data.csv")
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    df["label"] = df["company"] + " (" + df["ticker"] + ")"
    return df, meta


def r_square(x: pd.Series, y: pd.Series) -> float:
    """두 값의 상관관계 R² (0~1). 데이터가 부족하면 nan."""
    m = x.notna() & y.notna()
    if m.sum() < 3 or x[m].std() == 0 or y[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(x[m], y[m])[0, 1] ** 2)


def best_relationship(df: pd.DataFrame) -> tuple[str, str, float]:
    """이 그룹에서 R²가 가장 높은 X·멀티플 조합을 찾는다."""
    best = ("", "", -1.0)
    for xl, xc in X_AXES.items():
        for yl, yc in MULTIPLES.items():
            r2 = r_square(df[xc], df[yc])
            if not np.isnan(r2) and r2 > best[2]:
                best = (xl, yl, r2)
    return best


def scatter(df: pd.DataFrame, x_col: str, y_col: str, x_label: str, y_label: str,
            x_min: float, y_max: float, pick: pd.DataFrame | None = None) -> alt.Chart:
    """산점도: 조건 통과는 파랑, 나머지는 연한 색, 선택 종목은 주황 별."""
    d = df[df[x_col].notna() & df[y_col].notna() & (df[y_col] > 0)].copy()
    # 극단값은 차트를 망가뜨리므로 표시 범위만 잘라낸다 (데이터는 그대로)
    if len(d) > 20:
        x_lo, x_hi = d[x_col].quantile([0.01, 0.99])
        y_hi = d[y_col].quantile(0.99)
        d = d[(d[x_col] >= x_lo) & (d[x_col] <= x_hi) & (d[y_col] <= max(y_hi, y_max))]
    d["통과"] = (d[x_col] > x_min) & (d[y_col] < y_max)

    base = alt.Chart(d).mark_circle(size=55, opacity=0.75).encode(
        x=alt.X(x_col, title=f"{x_label} (높을수록 좋은 회사)", axis=alt.Axis(format="%")),
        y=alt.Y(y_col, title=f"{y_label} (낮을수록 싼 주식)"),
        color=alt.condition(alt.datum["통과"], alt.value(C_MATCH), alt.value(C_PEER)),
        tooltip=[alt.Tooltip("company", title="회사"),
                 alt.Tooltip("ticker", title="티커"),
                 alt.Tooltip(x_col, title=x_label, format=".1%"),
                 alt.Tooltip(y_col, title=y_label, format=".2f"),
                 alt.Tooltip("sector", title="섹터")],
    )
    rule_x = alt.Chart(pd.DataFrame({"v": [x_min]})).mark_rule(
        strokeDash=[5, 4], color="#888").encode(x="v")
    rule_y = alt.Chart(pd.DataFrame({"v": [y_max]})).mark_rule(
        strokeDash=[5, 4], color="#888").encode(y="v")
    layers = [base, rule_x, rule_y]

    if pick is not None and not pick.empty:
        p = pick[pick[x_col].notna() & pick[y_col].notna()]
        if not p.empty:
            layers.append(alt.Chart(p).mark_point(
                shape="diamond", size=320, filled=True, color=C_PICK,
                stroke="white", strokeWidth=1.5,
            ).encode(x=x_col, y=y_col,
                     tooltip=[alt.Tooltip("company", title="회사"),
                              alt.Tooltip(x_col, title=x_label, format=".1%"),
                              alt.Tooltip(y_col, title=y_label, format=".2f")]))
            layers.append(alt.Chart(p).mark_text(
                dy=-16, fontSize=13, fontWeight="bold", color=C_PICK,
            ).encode(x=x_col, y=y_col, text="company"))

    return alt.layer(*layers).properties(height=460).interactive()


def match_table(d: pd.DataFrame, x_col: str, y_col: str, x_label: str, y_label: str,
                key: str = "dl"):
    """조건 통과 종목 표 + CSV 다운로드."""
    t = d[["company", "ticker", "sector", x_col, y_col, "mcap"]].copy()
    t = t.sort_values(y_col)
    t[x_col] = (t[x_col] * 100).round(1)
    t[y_col] = t[y_col].round(2)
    t["mcap"] = (t["mcap"] / 1000).round(0)  # KRW mm -> KRW bn
    t.columns = ["회사", "티커", "섹터", f"{x_label} (%)", y_label, "시총(십억원)"]
    st.dataframe(t, use_container_width=True, hide_index=True, height=320)
    st.download_button("⬇️ CSV로 받기", t.to_csv(index=False).encode("utf-8-sig"),
                       "screener_matches.csv", "text/csv", key=key)


df, meta = load()

st.title("📊 밸류 스크리너")
st.caption(f"한국 상장사 {meta['n_companies']:,}개 · 기준일 {meta['as_of']} · "
           "X축 = 회사의 질(수익성+성장), Y축 = 주가의 비싼 정도(멀티플). "
           "**오른쪽 아래**에 있을수록 '좋은데 싼' 주식입니다.")

tab1, tab2 = st.tabs(["🔍 티커 조회", "🧮 조건 검색"])

# ================================================= 1) Ticker Input
with tab1:
    c1, c2 = st.columns([1, 2.2], gap="large")
    with c1:
        pick_label = st.selectbox("종목 (이름이나 티커로 검색)", df["label"].sort_values(),
                                  index=None, placeholder="예: SILICON2 또는 A257720")
        class_label = st.selectbox("피어그룹 기준 (분류 단계)", list(CLASS_LEVELS), index=0,
                                   help="선택한 회사와 같은 분류에 속한 회사들을 비교 대상으로 잡습니다. "
                                        "아래로 갈수록 더 좁고 비슷한 그룹입니다.")
        y_label1 = st.selectbox("멀티플 (Y축)", list(MULTIPLES), index=0, key="ti_y")
        x_label1 = st.selectbox("X축", list(X_AXES), index=0, key="ti_x")
        x_min1 = st.number_input(f"{x_label1} 이상 (%)", value=0.0, step=5.0, key="ti_xmin") / 100
        y_max1 = st.number_input(f"{y_label1} 이하", value=DEFAULT_Y_MAX[y_label1],
                                 step=0.5, key="ti_ymax")

    if pick_label is None:
        with c2:
            st.info("왼쪽에서 종목을 선택하면 피어그룹 차트가 나옵니다.")
    else:
        pick = df[df["label"] == pick_label]
        row = pick.iloc[0]
        class_col = CLASS_LEVELS[class_label]
        peers = df[df[class_col] == row[class_col]]
        x_col, y_col = X_AXES[x_label1], MULTIPLES[y_label1]

        with c1:
            st.markdown(f"**{row['company']}**")
            st.markdown(f"- 섹터: {row['sector']}\n- 산업: {row['industry']}\n"
                        f"- 피어그룹: {row[class_col]} ({len(peers)}개사)")
            bx, by, br2 = best_relationship(peers)
            r2 = r_square(peers[x_col], peers[y_col])
            st.markdown(f"- 현재 조합 R²: {r2:.1%}" if not np.isnan(r2) else "- 현재 조합 R²: 계산 불가")
            if br2 > 0:
                st.caption(f"이 그룹에서 설명력이 가장 높은 조합: X {bx} · Y {by} (R² {br2:.1%})")

        with c2:
            st.altair_chart(scatter(peers, x_col, y_col, x_label1, y_label1,
                                    x_min1, y_max1, pick=pick), use_container_width=True)
            mine = pick.iloc[0]
            vx = f"{mine[x_col]:.1%}" if pd.notna(mine[x_col]) else "없음"
            vy = f"{mine[y_col]:.2f}" if pd.notna(mine[y_col]) else "없음"
            st.caption(f"🔶 {row['company']}: {x_label1} {vx} · {y_label1} {vy}")

        good = peers[(peers[x_col] > x_min1) & (peers[y_col] > 0) & (peers[y_col] < y_max1)]
        st.markdown(f"#### 조건 통과 (좋은데 싼) 피어: {len(good)}개")
        match_table(good, x_col, y_col, x_label1, y_label1, key="dl_ticker")

# ================================================= 2) Screen Panel
with tab2:
    c1, c2 = st.columns([1, 2.2], gap="large")
    with c1:
        y_label2 = st.selectbox("멀티플 (Y축)", list(MULTIPLES), index=1, key="sp_y")
        x_label2 = st.selectbox("X축", list(X_AXES), index=0, key="sp_x")

        # 분류 필터 — 위에서 고르면 아래 선택지가 그 안으로 좁혀진다
        filt = df
        for lvl_label, lvl_col in CLASS_LEVELS.items():
            opts = ["(전체)"] + sorted(filt[lvl_col].dropna().unique())
            sel = st.selectbox(lvl_label, opts, key=f"sp_{lvl_col}")
            if sel != "(전체)":
                filt = filt[filt[lvl_col] == sel]

        x_min2 = st.number_input(f"{x_label2} 이상 (%)", value=20.0, step=5.0, key="sp_xmin") / 100
        y_max2 = st.number_input(f"{y_label2} 이하", value=DEFAULT_Y_MAX[y_label2],
                                 step=0.5, key="sp_ymax")

    x_col, y_col = X_AXES[x_label2], MULTIPLES[y_label2]
    good = filt[(filt[x_col] > x_min2) & (filt[y_col] > 0) & (filt[y_col] < y_max2)]

    with c1:
        r2 = r_square(filt[x_col], filt[y_col])
        st.markdown(f"**대상 {len(filt):,}개사 · 조건 통과 {len(good)}개**")
        if not np.isnan(r2):
            st.caption(f"R² {r2:.1%} — X와 멀티플의 상관 정도")

    with c2:
        st.altair_chart(scatter(filt, x_col, y_col, x_label2, y_label2, x_min2, y_max2),
                        use_container_width=True)

    st.markdown(f"#### 조건 통과 종목: {len(good)}개")
    match_table(good, x_col, y_col, x_label2, y_label2, key="dl_screen")

st.divider()
st.caption("데이터: Capital IQ 기반 비교기업 워크북에서 추출 · 멀티플이 0 이하(적자 등)인 종목은 "
           "조건 검색에서 제외됩니다 · 차트는 보기 좋게 극단값(상하위 1%)을 잘라서 그립니다.")
