# -*- coding: utf-8 -*-
"""제약 숏 스크리너 — 전통 제네릭 제약사 숏 후보 스크린 (Bio/Healthcare).

동국제약 롱 아이디어의 헤지: '전통 제네릭 제약' 다운사이드를 숏으로 상쇄할
후보를 4가지 조건으로 거른다. 데이터는 pharma-short 파이프라인이 만든
data/pharma_short/pharma_short.csv (갱신: step1→step2 재실행 후 push).
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "pharma_short"

st.set_page_config(page_title="제약 숏 스크리너", page_icon="💊", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("bio")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 1.18rem; font-weight: 600; background: #2a4a73;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 6px 12px; margin: 0.9rem 0 0.5rem 0;
}
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
.cond-chip {
    display: inline-block; background: #16223a; border: 1px solid #2a4a73;
    border-radius: 6px; padding: 6px 12px; margin: 3px 6px 3px 0;
    font-size: 0.86rem; color: #c6d0de;
}
.cond-chip b { color: #7cb3ff; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def load():
    df = pd.read_csv(DATA / "pharma_short.csv")
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    df["naver"] = ("https://finance.naver.com/item/main.naver?code="
                   + df["ticker"].str.lstrip("A"))
    return df, meta


df, meta = load()
C_BLUE, C_ORANGE, C_RED, C_GREY = "#2a78d6", "#eb6834", "#d43a2f", "#5f7089"

st.title("💊 제약 숏 스크리너 — 전통 제네릭 리스크")
st.caption(f"한국 상장 제약사 **{meta['n_companies']}개사** · 기준일 {meta['as_of']} · "
           "동국제약(🔶 비교 기준) 롱의 반대편 — '전통 제네릭' 다운사이드를 숏으로 "
           "헤지할 후보를 4가지 조건으로 거릅니다. 조건을 많이 충족할수록 위험한 회사.")

st.markdown(
    '<div class="cond-chip"><b>C1 커머디티</b> 제네릭 OTC·ETC가 본업 (믹스등급 A)</div>'
    f'<div class="cond-chip"><b>C2 저R&D</b> R&D/매출 &lt; {meta["rnd_threshold"]:.0f}% '
    f'(업계 평균 {meta["sector_avg_rnd"]}%)</div>'
    f'<div class="cond-chip"><b>C3 지배구조</b> 리스크 점수 ≥ {meta["gov_threshold"]} '
    '(횡령·리베이트·CB·승계)</div>'
    f'<div class="cond-chip"><b>C4 고평가</b> 멀티플 백분위 ≥ '
    f'{int(meta["val_threshold"]*100)}% (PER·PBR·EV/EBIT·EV/Sales)</div>',
    unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("4/4 충족 (최우선)", f"{int((df['n_cond'] == 4).sum())}개사")
m2.metric("3/4 충족", f"{int((df['n_cond'] == 3).sum())}개사")
m3.metric("업계 평균 R&D/매출", f"{meta['sector_avg_rnd']}%",
          help="상장 제약사 65개사 FY2025 집계 (의학신문 2026-04-06)")
m4.metric("유니버스 중앙값 R&D", f"{df['rnd_ratio'].median():.1f}%")

# ================================================= scatter
sub("📉 산점도 — 왼쪽 위가 위험 구역", "X = R&D 투자, Y = 밸류에이션")
c1, c2 = st.columns([1, 3.4], gap="large")
MULT = {"PBR": "pbr", "PER": "per", "EV/EBIT": "ev_ebit", "EV/Sales": "ev_sales"}
with c1:
    y_label = st.selectbox("Y축 (멀티플)", list(MULT), index=0)
    y_col = MULT[y_label]
    only3 = st.toggle("3조건+ 충족만 라벨", value=True)
    st.caption("점 크기 = 시총. 색 = 충족 조건 수. 🔶 = 동국제약(비교 기준). "
               "회색 세로 점선 = 저R&D 기준 5%, 파란 세로 점선 = 업계 평균 "
               f"{meta['sector_avg_rnd']}%. 점 클릭 = 네이버금융.")
d = df[df["rnd_ratio"].notna() & df[y_col].notna() & (df[y_col] > 0)].copy()
d["조건"] = d["n_cond"].astype(int).astype(str) + "/4"
y_hi = float(d[y_col].quantile(0.95)) * 1.6
cut = d[d[y_col] > y_hi]
d = d[d[y_col] <= y_hi]
if len(cut):
    _names = " · ".join(f"{r['name']} ({r[y_col]:.1f}배)"
                        for _, r in cut.sort_values(y_col, ascending=False).iterrows())
    st.warning(f"⚠️ 차트 범위 밖 (너무 비싸서 잘림, {y_label} 기준): {_names} — "
               "아래 랭킹 표에는 그대로 있습니다.")
base = alt.Chart(d).mark_circle(opacity=0.85, cursor="pointer").encode(
    x=alt.X("rnd_ratio", title="R&D / 매출 (%, FY2025 사업보고서)"),
    y=alt.Y(y_col, title=f"{y_label} (높을수록 비싸다)"),
    size=alt.Size("mcap", title="시총", scale=alt.Scale(range=[60, 900]),
                  legend=None),
    color=alt.Color("n_cond:O", title="충족 조건",
                    scale=alt.Scale(domain=[0, 1, 2, 3, 4],
                                    range=["#3d5878", "#5f7089", "#9ab6d8",
                                           "#e8a13a", "#d43a2f"])),
    href="naver:N",
    tooltip=[alt.Tooltip("name", title="회사"),
             alt.Tooltip("ticker", title="티커"),
             alt.Tooltip("rnd_ratio", title="R&D/매출 %", format=".1f"),
             alt.Tooltip(y_col, title=y_label, format=".2f"),
             alt.Tooltip("mix_grade", title="믹스등급"),
             alt.Tooltip("gov_score", title="지배구조점수"),
             alt.Tooltip("n_cond", title="충족 조건 수"),
             alt.Tooltip("score_total", title="종합점수")])
labels = alt.Chart(d[d["n_cond"] >= (3 if only3 else 0)]).mark_text(
    dy=-11, fontSize=11, fontWeight="bold", color="#e8a13a",
).encode(x="rnd_ratio", y=y_col, text="name")
rule5 = alt.Chart(pd.DataFrame({"v": [meta["rnd_threshold"]]})).mark_rule(
    strokeDash=[5, 4], color="#888").encode(x="v")
rule_avg = alt.Chart(pd.DataFrame({"v": [meta["sector_avg_rnd"]]})).mark_rule(
    strokeDash=[2, 3], color=C_BLUE).encode(x="v")
ref = d[d["is_ref"]]
ref_pt = alt.Chart(ref).mark_point(shape="diamond", size=340, filled=True,
                                   color=C_ORANGE, stroke="white",
                                   strokeWidth=1.5).encode(
    x="rnd_ratio", y=y_col,
    tooltip=[alt.Tooltip("name", title="회사"),
             alt.Tooltip("rnd_ratio", title="R&D/매출 %", format=".1f"),
             alt.Tooltip(y_col, title=y_label, format=".2f")])
ref_tx = alt.Chart(ref).mark_text(dy=-15, fontSize=12, fontWeight="bold",
                                  color=C_ORANGE).encode(x="rnd_ratio", y=y_col,
                                                         text="name")
with c2:
    ch = alt.layer(base, rule5, rule_avg, labels, ref_pt, ref_tx) \
            .properties(height=560).interactive()
    ch.usermeta = {"embedOptions": {"loader": {"target": "_blank"}}}
    st.altair_chart(ch, use_container_width=True)

# ================================================= ranking table
sub("🏁 숏 후보 랭킹", "충족 조건 수 → 종합점수 순")
t = df.copy()
for c, mark in [("c1_mix", "C1"), ("c2_rnd", "C2"), ("c3_gov", "C3"),
                ("c4_val", "C4")]:
    t[mark] = np.where(t[c], "✔", "")
t["시총(KRWbn)"] = (t["mcap"] / 1000).round(0).astype("Int64")
t["R&D/매출(%)"] = t["rnd_ratio"].round(1)
t["회사"] = np.where(t["is_ref"], "🔶 " + t["name"], t["name"])
show = t[["회사", "ticker", "시총(KRWbn)", "mix_grade", "R&D/매출(%)",
          "gov_score", "per", "pbr", "ev_ebit", "ev_sales",
          "C1", "C2", "C3", "C4", "n_cond", "score_total", "naver"]].copy()
show.columns = ["회사", "티커", "시총(KRWbn)", "믹스", "R&D/매출(%)", "지배구조",
                "PER", "PBR", "EV/EBIT", "EV/Sales", "C1", "C2", "C3", "C4",
                "충족", "종합점수", "네이버금융"]
for c in ["PER", "PBR", "EV/EBIT", "EV/Sales"]:
    show[c] = show[c].round(2)
st.dataframe(show, use_container_width=True, hide_index=True, height=560,
             column_config={"네이버금융": st.column_config.LinkColumn(
                 "네이버금융", display_text="📈")})
st.download_button("⬇️ CSV로 받기", show.to_csv(index=False).encode("utf-8-sig"),
                   "pharma_short_screen.csv", "text/csv")

# ================================================= detail
sub("🔎 회사별 근거 — 사업 믹스 · 지배구조 플래그", "출처 포함")
sel = st.selectbox("회사 선택", df["name"].tolist(),
                   index=int(df.index[df["n_cond"] == df["n_cond"].max()][0]))
row = df[df["name"] == sel].iloc[0]
d1, d2 = st.columns(2, gap="large")
with d1:
    st.markdown(f"**사업 구성** — 믹스등급 **{row['mix_grade']}** "
                f"(A=커머디티 제네릭 · B=혼합 · C=차별화)")
    st.markdown(f"- {row['mix_note']}")
    parts = []
    for k, lbl in [("otc_pct", "OTC"), ("etc_pct", "ETC"), ("other_pct", "기타")]:
        if pd.notna(row[k]):
            parts.append(f"{lbl} {row[k]:.0f}%")
    if parts:
        st.markdown("- 매출 비중: " + " · ".join(parts) + f" ({row['fy']})")
    st.caption(f"출처: {row['source']}")
    st.markdown(f"**R&D/매출: {row['rnd_ratio']:.1f}%** "
                f"(FY2025 사업보고서 보고치 · 업계 평균 {meta['sector_avg_rnd']}%)")
    if pd.notna(row["rnd_krwmn"]):
        st.caption(f"R&D {row['rnd_krwmn']:,.0f} KRWmn / "
                   f"매출 {row['revenue_krwmn']:,.0f} KRWmn · "
                   f"DART 접수번호 {row['rcept_no']}")
with d2:
    st.markdown(f"**지배구조 리스크 점수: {row['gov_score']:.0f} / 100** (수기 평가)")
    if isinstance(row["flags"], str) and row["flags"]:
        for f in str(row["flags"]).split(";"):
            st.markdown(f"- 🚩 {f.strip()}")
    else:
        st.markdown("- 주요 플래그 없음")
    if isinstance(row["notes"], str):
        st.markdown(f"{row['notes']}")
    st.caption(f"출처: {row['sources']}")

st.divider()
st.caption("**방법론**: 종합점수 = 0.25×믹스 + 0.20×R&D + 0.25×지배구조 + 0.30×밸류 "
           "(각 0-100, 높을수록 숏 후보). 밸류 백분위는 이 42개사 안에서의 상대 순위. · "
           "**데이터**: R&D/매출 = DART 사업보고서 FY2025 '연구개발비용' 표의 보고 비율 "
           "(뉴스 집계와 교차검증) · 멀티플·시총 = Capital IQ 비교기업 워크북 "
           "(2026E 컨센서스, 없으면 LTM — 밸류 스크리너와 동일 원본) · "
           "사업 믹스·지배구조 = 뉴스·공시 리서치 (일부 '미확인' 항목 포함, 수기 점수는 "
           "정성 판단). · **주의**: 이 화면은 후보 스크린이지 매매 지시가 아닙니다. "
           "공매도 가능 여부·대차 잔고·수급은 별도 확인 필요. "
           "갱신: pharma-short 파이프라인 step1→step2 재실행 후 push.")
