# -*- coding: utf-8 -*-
"""2차전지·EV·ESS 수급 트래커 — 입문서 [표 D-7]의 6개 지표 루틴.

데이터: batt-tracker 폴더(엑셀 원본)에서 batt_update.py 로 복사한 data/batt/*.csv
- 자동: EIA-860M 미국 ESS 설치량, DART 셀 3사 수주 공시
- 수기: SNE 사용량·점유율, 리튬 현물가, 관세청 수출단가, AMPC, 정책 캘린더
        (워크북과 같은 manual_*.csv — 수기 갱신은 batt-tracker 쪽에서)
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "batt"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"

st.set_page_config(page_title="2차전지 수급", page_icon="🔋", layout="wide")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 0.97rem; font-weight: 700; background: #16283e;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 6px 12px; margin: 0.9rem 0 0.5rem 0;
}
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def load(name, **kw):
    p = DATA / name
    if not p.exists():
        return None
    return pd.read_csv(p, **kw)


st.title("2차전지 · EV · ESS 수급 트래커")
meta = {}
if (DATA / "fetch_meta.json").exists():
    meta = json.loads((DATA / "fetch_meta.json").read_text(encoding="utf-8"))
st.caption("입문서 [표 D-7] '혼자서 수급을 확인하는 6개 지표' 루틴 · "
           f"자동 수집 {meta.get('fetched', '—')[:10]} (EIA·DART) · "
           "수기 지표는 워크북(2차전지_수급_Tracker)과 동일 데이터")

st.info("**D장 요약** — ① 배터리 공장은 전 세계에 남아돈다 ② 그런데 '미국 세액공제 "
        "적격 비중국산 LFP'는 모자란다 (2028년 한국 캐파를 다 지어도 30% 부족) "
        "③ 진짜 병목은 배터리가 아니라 **전기**(계통접속 2,060GW 대기, 완공률 13%)와 "
        "**인증**(화재시험 6~12개월)이다.")

tab_dem, tab_ess, tab_pol = st.tabs(
    ["📊 수요·가격 (지표 1~3)", "🔋 미국 ESS (지표 4)", "📋 수주·정책 (지표 5~6)"])

# ================================================================ 지표 1~3
with tab_dem:
    # ---- 1. 글로벌 사용량 / 한국 3사 점유율
    sub("① 글로벌 배터리 사용량 (중국 제외)",
        "SNE Research → 증권사 Monthly · 월간 · 한국 3사 점유율이 27.6%에서 오르는지")
    us = load("manual_usage.csv", dtype=str)
    if us is not None:
        rows = us[us["중국제외(GWh)"].notna() & (us["중국제외(GWh)"] != "")]
        m1, m2, m3 = st.columns(3)
        if len(rows):
            r = rows.iloc[-1]
            share = (float(r["한국3사_중국제외(GWh)"]) / float(r["중국제외(GWh)"]) * 100)
            m1.metric(f"한국 3사 중국제외 M/S ({r['연도']} {r['기간']})",
                      f"{share:.1f}%", "기준선 27.6% — 오르면 반격", delta_color="off")
            m2.metric("중국제외 시장", f"{float(r['중국제외(GWh)']):,.0f}GWh")
            m3.metric("글로벌", f"{float(r['글로벌(GWh)']):,.0f}GWh", "+19.9% YoY",
                      delta_color="off")
        st.caption("맥락: CATL이 중국제외 시장에서도 33.6%로 1위(+41.7% YoY). 유럽 내 "
                   "한국 3사 몫은 55%(2023)→30%(2026 상반기)로 반토막. | 매달 SNE "
                   "보도자료가 나오면 워크북 1_사용량 시트(manual_usage.csv)에 행 추가.")

    c1, c2 = st.columns(2, gap="large")
    # ---- 2. 탄산리튬 현물가
    with c1:
        sub("② 탄산리튬 현물가", "SMM/광해광업공단 · 일간 · 양극재 실적의 선행지표")
        li = load("manual_lithium.csv")
        if li is not None and len(li):
            li = li.copy()
            li["date"] = pd.to_datetime(li["월"])
            cur = li.iloc[-1]
            st.metric(f"최근 ({cur['월']})", f"{cur['탄산리튬(CNY/t)']:,.0f} CNY/t",
                      "3Q26 컨센서스 밴드 150,000~170,000", delta_color="off")
            band = alt.Chart(pd.DataFrame({"y": [150000], "y2": [170000]})).mark_rect(
                opacity=0.15, color=C_GOLD).encode(y="y:Q", y2="y2:Q")
            line = alt.Chart(li).mark_line(color=C_BAR, size=2.5, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("탄산리튬(CNY/t):Q", title="CNY/t",
                        scale=alt.Scale(zero=False)),
                tooltip=["월", alt.Tooltip("탄산리튬(CNY/t)", format=",.0f")])
            st.altair_chart(alt.layer(band, line).properties(height=280),
                            use_container_width=True)
            st.caption("금색 음영 = 컨센서스 밴드. 밴드 위 = 양극재 판가·재고이익 개선 "
                       "신호. 저점(2025.10 73,550) 대비 +127%.")

    # ---- 3. 양극재 수출단가
    with c2:
        sub("③ 한국 양극재 수출단가", "관세청 · 월간 · 리튬가에 2~5개월 후행")
        ex = load("manual_export.csv")
        if ex is not None and len(ex):
            ex = ex.copy()
            ex["date"] = pd.to_datetime(ex["월"])
            cur = ex.iloc[-1]
            st.metric(f"최근 ({cur['월']})", f"{cur['양극재전체($/kg)']:.1f} $/kg",
                      "2025.9월 저점 21.8 → 반등 유지 여부", delta_color="off")
            line = alt.Chart(ex).mark_line(color=C_BAR, size=2.5, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("양극재전체($/kg):Q", title="$/kg",
                        scale=alt.Scale(zero=False)),
                tooltip=["월", alt.Tooltip("양극재전체($/kg)", format=".1f")])
            low = alt.Chart(pd.DataFrame({"v": [21.8]})).mark_rule(
                color="#8894a6", strokeDash=[4, 3]).encode(y="v:Q")
            st.altair_chart(alt.layer(line, low).properties(height=280),
                            use_container_width=True)
            st.caption("점선 = 2025.9월 사이클 저점(21.8). 경로: 2023.1월 49.8 고점 → "
                       "저점 → 반등 중. NCM만 보면 2026.7월 28.1$/kg.")

# ================================================================ 지표 4
with tab_ess:
    sub("④ 미국 ESS 신규 설치량", "EIA·WoodMac·ACP · 분기 · 2025년 57.6GWh가 기준선, "
                                "계통접속 지연 여부가 핵심")
    g = load("manual_us_ess_gwh.csv", dtype=str)
    mo = load("us_ess_monthly.csv")
    pl = load("us_ess_pipeline.csv")
    if mo is not None:
        eia25 = mo[mo["year"] == 2025]["mwh"].sum() / 1000
        eia26 = mo[mo["year"] == 2026]["mwh"].sum() / 1000
        n26 = mo[mo["year"] == 2026]["month"].max()
        m1, m2, m3 = st.columns(3)
        m1.metric("2025년 설치 (ACP·WoodMac 기준)", "57.6 GWh", "사상 최대 · 85% 유틸리티급",
                  delta_color="off")
        m2.metric("2025년 운전개시 (EIA-860M 기준)", f"{eia25:.1f} GWh",
                  "집계 기준이 달라 ACP보다 작게 잡힘", delta_color="off")
        m3.metric(f"2026년 1~{int(n26)}월 운전개시 (EIA)", f"{eia26:.1f} GWh",
                  f"연환산 {eia26 / n26 * 12:.0f} GWh 페이스", delta_color="off")

    e1, e2 = st.columns(2, gap="large")
    with e1:
        sub("연간 설치량 — 실적과 전망", "유안타(2026.6.24) Base/Low/High 시나리오")
        if g is not None:
            gg = g.copy()
            gg["v"] = gg["설치량(GWh)"].astype(float)
            bars = alt.Chart(gg).mark_bar(opacity=0.9).encode(
                x=alt.X("연도:N", sort=None, title=None),
                y=alt.Y("v:Q", title="설치량 (GWh)"),
                color=alt.Color("구분:N", scale=alt.Scale(domain=["실적", "Base"],
                                                        range=[C_BAR, C_LINE]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["연도", "구분", alt.Tooltip("v", format=".1f", title="GWh")])
            err_df = gg[gg["Low"].notna() & (gg["Low"] != "")].copy()
            layers = [bars]
            if len(err_df):
                err_df["lo"] = err_df["Low"].astype(float)
                err_df["hi"] = err_df["High"].astype(float)
                layers.append(alt.Chart(err_df).mark_rule(color="#c9d4e4", size=2).encode(
                    x="연도:N", y="lo:Q", y2="hi:Q",
                    tooltip=["연도", alt.Tooltip("lo", title="Low"),
                             alt.Tooltip("hi", title="High")]))
            st.altair_chart(alt.layer(*layers).properties(height=320),
                            use_container_width=True)
            st.caption("세로선 = Low~High 시나리오 범위. 2030년 Base 115.4GWh = "
                       "2025년의 2배.")
    with e2:
        sub("월별 운전개시 — EIA-860M (자동 수집)", "명판 에너지용량(MWh) 합, COD 기준")
        if mo is not None:
            m = mo.copy()
            m = m[m["year"] >= 2023]
            m["연월"] = m["year"].astype(str) + "-" + m["month"].astype(int).map("{:02d}".format)
            m["GWh"] = m["mwh"] / 1000
            ch = alt.Chart(m).mark_bar(color=C_BAR, opacity=0.9).encode(
                x=alt.X("연월:N", sort=None, title=None,
                        axis=alt.Axis(labelAngle=-60)),
                y=alt.Y("GWh:Q", title="신규 운전개시 (GWh)"),
                tooltip=["연월", alt.Tooltip("GWh", format=".2f")])
            st.altair_chart(ch.properties(height=320), use_container_width=True)
            st.caption("들쭉날쭉한 달 = 대형 프로젝트 COD 몰림. 몇 달 연속 얇아지면 "
                       "계통접속 지연 신호.")
    if pl is not None and len(pl):
        sub("계획(Planned) 파이프라인", "EIA-860M Planned 시트 — 연도별 계획 용량 (MW)")
        pp = pl.copy()
        pp["GW"] = pp["mw"] / 1000
        ch = alt.Chart(pp).mark_bar(color=C_GOLD, opacity=0.85).encode(
            x=alt.X("year:N", title=None), y=alt.Y("GW:Q", title="계획 용량 (GW)"),
            tooltip=["year", alt.Tooltip("GW", format=".1f")])
        st.altair_chart(ch.properties(height=220), use_container_width=True)
        st.caption("계획 물량이 실제 COD로 이어지는 비율(완공률 13%)이 낮은 것 자체가 "
                   "공급을 조이는 요인. 계획 연도가 뒤로 밀리면 = 계통접속 지연.")

# ================================================================ 지표 5~6
with tab_pol:
    sub("⑤ 셀 3사 수주 공시 · AMPC", "DART 수시 · 수주는 'ESS·LFP·미국'이면 강한 신호 · "
                                  "AMPC 뺀 본업 이익을 반드시 따로 볼 것")
    od = load("orders.csv", dtype=str)
    if od is not None and len(od):
        t = od.copy()
        t["공시일"] = t["date"].str[:4] + "-" + t["date"].str[4:6] + "-" + t["date"].str[6:]
        t = t[["공시일", "company", "report", "url"]]
        t.columns = ["공시일", "회사", "보고서명", "DART"]
        st.dataframe(t, hide_index=True, use_container_width=True,
                     height=min(80 + 36 * len(t), 420),
                     column_config={"DART": st.column_config.LinkColumn(
                         "DART", display_text="📄 열기")})
        st.caption(f"최근 3년 수주·계약·투자 공시 {len(t)}건 (LG엔솔·삼성SDI·SK이노베이션). "
                   "batt_update.py 실행 시 자동 갱신.")
    st.warning("**AMPC 체크포인트** — 유안타(2026.6.24) p.152: AMPC(미국 생산세액공제)를 "
               "빼면 2026년 셀 본업은 여전히 적자. 분기 실적발표 때마다 'AMPC 인식액'과 "
               "'AMPC 제외 영업이익'을 워크북 5_수주_AMPC 시트에 기록할 것.")

    sub("⑥ 미국·EU 정책 캘린더", "IRS Notice·EU 집행위 · 수시 · MACR 상향, IAA 채택, "
                              "전력망 시행규칙이 3대 관찰 포인트")
    po = load("manual_policy.csv", dtype=str)
    if po is not None:
        t = po[["지역", "제도", "내용", "시점", "상태"]].copy()
        _badge = {"진행": "🟢 진행", "예정": "🟡 예정", "관찰": "👁 관찰",
                  "종료": "⚫ 종료", "시행": "🟢 시행"}
        t["상태"] = t["상태"].map(lambda x: _badge.get(x, x))
        st.dataframe(t, hide_index=True, use_container_width=True,
                     height=80 + 36 * len(t))
        st.caption("핵심 스케줄: MACR 55%(2026)→60%(2027)→65%(2028)→75%+(2030) · "
                   "45X 축소 2030년 75%→2033년 0% · 중국 리튬전지 소비세 2026.9월 2%→"
                   "2027.9월 4%. 새 Notice/규칙이 나오면 워크북 6_정책 시트에 추가.")

st.divider()
st.caption("데이터: EIA-860M(미국 설치, 자동)·DART(수주 공시, 자동)은 batt_update.py, "
           "나머지는 워크북 2차전지_수급_Tracker와 공유하는 수기 CSV. 설치량·출하량·"
           "캐파는 정의가 달라 절대 섞지 않음. 숫자는 참고용.")
