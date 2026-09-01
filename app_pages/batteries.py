# -*- coding: utf-8 -*-
"""2차전지·EV·ESS 수급 트래커 — 입문서 [표 D-7]의 6개 지표 루틴 (상세판).

데이터:
- IBK Monthly PDF 파싱 (parse_ibk_monthly.py): 지역·기업별 배터리 출하량,
  EV 판매, 침투율 — 원출처 SNE Research
- EIA-860M(미국 ESS)·DART(수주 공시): fetch_data.py 자동 수집
- 수기: 리튬 현물가, 수출단가, AMPC, 정책 (manual_*.csv, 워크북과 공유)
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "batt"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"
C_K3 = {"LGES": "#2a78d6", "SK On": "#8ec9ff", "SDI": "#4fb8c9",
        "CATL": "#eb6834", "Panasonic": "#b5b5b5", "etc": "#5f7089"}

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


def monthly_wide(name):
    """(series,year,month,value) 롱 CSV -> 날짜 인덱스 와이드."""
    d = load(name)
    if d is None:
        return None
    d = d.copy()
    d["date"] = pd.to_datetime(d["year"].astype(str) + "-"
                               + d["month"].astype(str) + "-01")
    return d


st.title("2차전지 · EV · ESS 수급 트래커")
meta = {}
if (DATA / "fetch_meta.json").exists():
    meta = json.loads((DATA / "fetch_meta.json").read_text(encoding="utf-8"))
st.caption("입문서 [표 D-7] '혼자서 수급을 확인하는 6개 지표' 루틴 · "
           "월별 상세 = SNE Research (IBK Monthly 2026.8.4 파싱) · "
           f"자동 수집 {meta.get('fetched', '—')[:10]} (EIA·DART)")

st.info("**D장 요약** — ① 배터리 공장은 전 세계에 남아돈다 ② 그런데 '미국 세액공제 "
        "적격 비중국산 LFP'는 모자란다 (2028년 한국 캐파를 다 지어도 30% 부족) "
        "③ 진짜 병목은 배터리가 아니라 **전기**(계통접속 2,060GW 대기, 완공률 13%)와 "
        "**인증**(화재시험 6~12개월)이다.")

tab_dem, tab_ev, tab_ess, tab_pol = st.tabs(
    ["📊 배터리 수급 (지표 1~3)", "🚗 EV 판매·침투율", "🔋 미국 ESS (지표 4)",
     "📋 수주·정책 (지표 5~6)"])

# ================================================================ 지표 1~3
with tab_dem:
    sub("① 글로벌 배터리 사용량 (중국 제외) — 한국 3사 점유율",
        "SNE Research → IBK Monthly · 월간 · 기준선 27.6%에서 오르는지")
    ex = monthly_wide("batt_ship_exchina.csv")
    rg = monthly_wide("batt_ship_region.csv")
    if ex is not None:
        w = ex.pivot_table(index="date", columns="series", values="value")
        w["한국 3사"] = w["LGES"] + w["SK On"] + w["SDI"]
        w["MS"] = w["한국 3사"] / w["Grand Total"] * 100
        w["CATL_MS"] = w["CATL"] / w["Grand Total"] * 100
        cur = w.dropna(subset=["MS"]).iloc[-1]
        m1, m2, m3 = st.columns(3)
        m1.metric(f"한국 3사 중국제외 M/S ({cur.name:%Y-%m})", f"{cur['MS']:.1f}%",
                  "기준선 27.6% (2026 상반기 누적)", delta_color="off")
        m2.metric("CATL 중국제외 M/S", f"{cur['CATL_MS']:.1f}%",
                  "중국제외 시장에서도 1위", delta_color="off")
        m3.metric("중국제외 시장 (월)", f"{cur['Grand Total']:.1f}GWh")

        g1, g2 = st.columns(2, gap="large")
        with g1:
            ms = w[["MS", "CATL_MS"]].reset_index().melt("date", var_name="s",
                                                         value_name="v").dropna()
            ms["s"] = ms["s"].map({"MS": "한국 3사", "CATL_MS": "CATL"})
            line = alt.Chart(ms).mark_line(size=2.5, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("v:Q", title="중국제외 M/S (%)", scale=alt.Scale(zero=False)),
                color=alt.Color("s:N", scale=alt.Scale(domain=["한국 3사", "CATL"],
                                                       range=[C_BAR, C_LINE]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=[alt.Tooltip("date:T"), "s", alt.Tooltip("v", format=".1f")])
            base27 = alt.Chart(pd.DataFrame({"v": [27.6]})).mark_rule(
                color=C_GOLD, strokeDash=[5, 4]).encode(y="v:Q")
            st.altair_chart(alt.layer(line, base27).properties(height=300),
                            use_container_width=True)
            st.caption("**읽는법**: 파랑(한국 3사)이 금색 점선(27.6%) 위로 올라서면 "
                       "'한국의 반격' 시나리오 작동. 주황(CATL)과의 격차가 좁혀지는지가 "
                       "관전 포인트 — CATL은 중국제외 시장에서도 이미 1위(+41.7% YoY).")
        with g2:
            comp = ex[ex["series"].isin(["CATL", "LGES", "SK On", "SDI",
                                         "Panasonic"])]
            line2 = alt.Chart(comp).mark_line(size=2, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("value:Q", title="월 출하량 (GWh, 중국제외)"),
                color=alt.Color("series:N",
                                scale=alt.Scale(domain=list(C_K3)[:5],
                                                range=[C_K3[k] for k in
                                                       list(C_K3)[:5]]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=[alt.Tooltip("date:T"), "series",
                         alt.Tooltip("value", format=".1f")])
            st.altair_chart(line2.properties(height=300), use_container_width=True)
            st.caption("**읽는법**: 기업별 월 출하량(중국제외). CATL 혼자 가파르게 "
                       "오르는 반면 LGES는 완만, SDI는 정체 — 점유율 격차의 실체. "
                       "자료: SNE Research (IBK Monthly).")
    if rg is not None:
        sub("지역별 배터리 출하량", "미국 역성장 여부와 유럽 반등이 핵심")
        r = rg[rg["series"].isin(["미국", "유럽", "중국", "기타"])]
        ch = alt.Chart(r).mark_area(opacity=0.75).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("value:Q", title="월 출하량 (GWh)", stack=True),
            color=alt.Color("series:N",
                            scale=alt.Scale(domain=["중국", "유럽", "미국", "기타"],
                                            range=["#eb6834", "#2a78d6",
                                                   "#4fb8c9", "#5f7089"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("date:T"), "series",
                     alt.Tooltip("value", format=".1f")])
        st.altair_chart(ch.properties(height=300), use_container_width=True)
        st.caption("**읽는법**: 지역별 적층 면적. 2026년 YTD 미국 −20.9%(세액공제 종료 "
                   "여파) vs 유럽 +28.3% vs 중국 +13.5% — '미국만 캐즘'을 배터리 "
                   "출하에서도 확인. 미국 면적이 다시 두꺼워지는 달이 반전 신호.")

    c1, c2 = st.columns(2, gap="large")
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
            st.caption("**읽는법**: 금색 음영 = 3Q26 컨센서스 밴드. 밴드 위에서 유지되면 "
                       "양극재 판가 인상 + 재고평가이익, 급락하면 재고평가손실 위험. "
                       "저점(2025.10 73,550) 대비 +127%. 수출단가가 2~5개월 후행.")
    with c2:
        sub("③ 한국 양극재 수출단가", "관세청(KITA) · 월간 · 리튬가에 2~5개월 후행")
        exp = load("manual_export.csv")
        if exp is not None and len(exp):
            exp = exp.copy()
            exp["date"] = pd.to_datetime(exp["월"])
            cur = exp.iloc[-1]
            st.metric(f"최근 ({cur['월']})", f"{cur['양극재전체($/kg)']:.1f} $/kg",
                      "2025.9월 저점 21.8 → 반등 유지 여부", delta_color="off")
            line = alt.Chart(exp).mark_line(color=C_BAR, size=2.5, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("양극재전체($/kg):Q", title="$/kg",
                        scale=alt.Scale(zero=False)),
                tooltip=["월", alt.Tooltip("양극재전체($/kg)", format=".1f")])
            low = alt.Chart(pd.DataFrame({"v": [21.8]})).mark_rule(
                color="#8894a6", strokeDash=[4, 3]).encode(y="v:Q")
            st.altair_chart(alt.layer(line, low).properties(height=280),
                            use_container_width=True)
            st.caption("**읽는법**: 점선 = 2025.9월 사이클 저점(21.8). 리튬가 반등이 "
                       "2~5개월 시차로 단가에 반영되는 중(2026.7월 27.8, NCM 28.1). "
                       "원출처는 KITA/관세청 무역통계 — IBK Monthly p.34~38이 소재별 "
                       "(NCM·전구체·동박·전해액·분리막) 수출입을 매달 전재.")

# ================================================================ EV 판매
with tab_ev:
    sub("지역별 전기차 판매", "SNE Research · 월간 · '미국만 캐즘'을 숫자로 확인")
    ev = monthly_wide("ev_sales_region.csv")
    pen = monthly_wide("ev_penetration.csv")
    if ev is not None:
        w = ev.pivot_table(index="date", columns="series", values="value")
        cur = w.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        _yoy = (w / w.shift(12) - 1) * 100
        for col, name in zip((m1, m2, m3, m4), ("글로벌", "미국", "유럽", "중국")):
            y = _yoy[name].iloc[-1]
            col.metric(f"{name} ({cur.name:%Y-%m})", f"{cur[name]:.0f}만대",
                       f"{y:+.1f}% YoY")
        e1, e2 = st.columns(2, gap="large")
        with e1:
            r = ev[ev["series"] != "글로벌"]
            ch = alt.Chart(r).mark_line(size=2.5, point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("value:Q", title="월 판매 (만대)"),
                color=alt.Color("series:N",
                                scale=alt.Scale(domain=["중국", "유럽", "미국"],
                                                range=["#eb6834", "#2a78d6",
                                                       "#4fb8c9"]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=[alt.Tooltip("date:T"), "series",
                         alt.Tooltip("value", format=".1f")])
            st.altair_chart(ch.properties(height=320), use_container_width=True)
            st.caption("**읽는법**: 미국(하늘색)은 2025.10월 세액공제 종료 후 "
                       "20.1만→8.1만대로 급락한 뒤 저공비행 — 캐즘 한복판. 유럽(파랑)은 "
                       "+29% 성장으로 이미 캐즘 통과. 중국(주황)은 내수 감속(−9.5%) 중 — "
                       "대신 수출이 +124%.")
        with e2:
            if pen is not None:
                p = pen[pen["series"] == "침투율"]
                ch = alt.Chart(p).mark_line(color=C_GOLD, size=2.5,
                                            point=True).encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("value:Q", title="글로벌 EV 침투율 (%)",
                            scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("date:T"),
                             alt.Tooltip("value", format=".1f", title="침투율")])
                st.altair_chart(ch.properties(height=320), use_container_width=True)
                st.caption("**읽는법**: 완성차 판매 중 EV 비중. 2026.6월 25.5% "
                           "(YoY +1.9%p) — 캐즘이라는 말과 달리 글로벌 침투율은 계속 "
                           "우상향. 문제는 속도와 지역 편차(미국 5%대 vs 중국 50%대).")
    st.caption("이 탭은 지표 ①(배터리 사용량)의 수요 원천을 보는 참고 화면. "
               "EV가 안 팔려도 ESS가 성장축을 대신하는지가 D장의 핵심 질문.")

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
        m1.metric("2025년 설치 (ACP·WoodMac 기준)", "57.6 GWh",
                  "사상 최대 · 85% 유틸리티급", delta_color="off")
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
                layers.append(alt.Chart(err_df).mark_rule(color="#c9d4e4",
                                                          size=2).encode(
                    x="연도:N", y="lo:Q", y2="hi:Q",
                    tooltip=["연도", alt.Tooltip("lo", title="Low"),
                             alt.Tooltip("hi", title="High")]))
            st.altair_chart(alt.layer(*layers).properties(height=320),
                            use_container_width=True)
            st.caption("**읽는법**: 세로선 = Low~High 시나리오 폭. 2030년 Base "
                       "115.4GWh = 2025년의 2배. High 시나리오와 Low의 차이는 대부분 "
                       "계통접속·관세 변수.")
    with e2:
        sub("월별 운전개시 — EIA-860M (자동 수집)", "명판 에너지용량(MWh), COD 기준")
        if mo is not None:
            m = mo.copy()
            m = m[m["year"] >= 2023]
            m["연월"] = (m["year"].astype(str) + "-"
                        + m["month"].astype(int).map("{:02d}".format))
            m["GWh"] = m["mwh"] / 1000
            ch = alt.Chart(m).mark_bar(color=C_BAR, opacity=0.9).encode(
                x=alt.X("연월:N", sort=None, title=None,
                        axis=alt.Axis(labelAngle=-60)),
                y=alt.Y("GWh:Q", title="신규 운전개시 (GWh)"),
                tooltip=["연월", alt.Tooltip("GWh", format=".2f")])
            st.altair_chart(ch.properties(height=320), use_container_width=True)
            st.caption("**읽는법**: 들쭉날쭉한 달 = 대형 프로젝트 COD 몰림(2026.6월 "
                       "10.4GWh처럼). 몇 달 연속 얇아지면 계통접속 지연 신호. ACP "
                       "설치량과 정의가 달라(EIA=COD, ACP=설치) 수치를 섞지 말 것.")
    if pl is not None and len(pl):
        sub("계획(Planned) 파이프라인", "EIA-860M Planned 시트 — 연도별 계획 용량 (MW)")
        pp = pl.copy()
        pp["GW"] = pp["mw"] / 1000
        ch = alt.Chart(pp).mark_bar(color=C_GOLD, opacity=0.85).encode(
            x=alt.X("year:N", title=None), y=alt.Y("GW:Q", title="계획 용량 (GW)"),
            tooltip=["year", alt.Tooltip("GW", format=".1f")])
        st.altair_chart(ch.properties(height=220), use_container_width=True)
        st.caption("**읽는법**: 계획→실제 COD 완공률이 13%에 불과한 것 자체가 공급을 "
                   "조이는 요인. 특정 연도의 막대가 다음 해로 밀리면 = 계통접속 지연이 "
                   "심해지고 있다는 뜻.")

# ================================================================ 지표 5~6
with tab_pol:
    sub("⑤ 셀 3사 수주 공시 · AMPC", "DART 수시 · 수주는 'ESS·LFP·미국'이면 강한 신호 · "
                                  "AMPC 뺀 본업 이익을 반드시 따로 볼 것")
    od = load("orders.csv", dtype=str)
    if od is not None and len(od):
        t = od.copy()
        t["공시일"] = (t["date"].str[:4] + "-" + t["date"].str[4:6] + "-"
                     + t["date"].str[6:])
        t = t[["공시일", "company", "report", "url"]]
        t.columns = ["공시일", "회사", "보고서명", "DART"]
        st.dataframe(t, hide_index=True, use_container_width=True,
                     height=min(80 + 36 * len(t), 420),
                     column_config={"DART": st.column_config.LinkColumn(
                         "DART", display_text="📄 열기")})
        st.caption(f"최근 3년 수주·계약·투자 공시 {len(t)}건 (LG엔솔·삼성SDI·"
                   "SK이노베이션). batt_update.py 실행 시 자동 갱신. "
                   "**읽는법**: 계약 상대·지역·화학조성을 열어 확인 — "
                   "'ESS·LFP·미국' 3박자면 AMPC 수혜 + 수급 타이트 구간 수주.")
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
        st.caption("**읽는법**: MACR 55%(2026)→60%(2027)→65%(2028)→75%+(2030) — "
                   "비율이 오를 때마다 비중국 소재 수요가 계단식으로 늘어남. 45X 축소는 "
                   "2030년 75%→2033년 0% — 셀 3사 이익의 소멸 시계. 새 IRS Notice가 "
                   "나오면 워크북 6_정책 시트에 날짜·링크 추가.")

st.divider()
st.caption("데이터: 월별 출하량·EV판매·침투율 = SNE Research (IBK Monthly PDF를 "
           "parse_ibk_monthly.py로 파싱, 새 Monthly가 나오면 PDF 경로만 넘겨 갱신) · "
           "미국 ESS = EIA-860M 자동 · 수주 공시 = DART 자동 · 리튬가·수출단가·AMPC·"
           "정책 = 수기(워크북 공유). 설치량·출하량·캐파는 정의가 달라 절대 섞지 않음.")
