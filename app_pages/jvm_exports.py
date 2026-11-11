# -*- coding: utf-8 -*-
"""제이브이엠(054950) 수출 트래커 — 관세청 무역통계 + DART 교차검증.

데이터: jvm_customs_fetch.py (관세청 tradedata.go.kr 직접 수집) + jvm_dart_exports.py (DART 매출실적).
핵심 지표 = HS 3920.71 (재생 셀룰로오스 필름 = ATDPS 파우치 원단). 전국 수출의 약 73% 가
대구 달서구(JVM 본사·공장)에서 나가고, 행선지가 JVM 시장과 같아 소모품 수출의 사실상 단독 지표.
기계(ATDPS 본체)는 HS 8479.89 '기타 기계'에 섞여 들어가 참고용으로만 둔다.
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "jvm"
USDKRW = {2016: 1160, 2017: 1131, 2018: 1100, 2019: 1166, 2020: 1180, 2021: 1144,
          2022: 1292, 2023: 1306, 2024: 1364, 2025: 1420, 2026: 1400}   # 연평균 근사 (findb_update.py 와 동일)

st.set_page_config(page_title="제이브이엠 수출 트래커", page_icon="🚢", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("bio")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 7px 14px; margin: 0.9rem 0 0.5rem 0; }
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
    return pd.read_csv(p) if p.exists() else None


_meta = {}
if (DATA / "customs_meta.json").exists():
    _meta = json.loads((DATA / "customs_meta.json").read_text(encoding="utf-8"))
_lm = _meta.get("latest_month", "")

st.title("제이브이엠 (054950) 수출 트래커 — 관세청 직접 수집")
st.caption(f"ATDPS 파우치 원단 HS 3920.71 · 월 × 국가 · US$ · 2016.01 ~ {_lm.replace('-', '.')} 확정통계 "
           "· DART 매출실적으로 교차검증 · [📋 제이브이엠 Stock Picker](종목상세?ticker=A054950)")

cons = load("customs_392071_monthly.csv", _stamp("customs_392071_monthly.csv"))
mach = load("customs_847989_monthly.csv", _stamp("customs_847989_monthly.csv"))
dal = load("customs_dalseo_monthly.csv", _stamp("customs_dalseo_monthly.csv"))
dq = load("dart_exports_quarterly.csv", _stamp("dart_exports_quarterly.csv"))
da = load("dart_exports_annual.csv", _stamp("dart_exports_annual.csv"))
if cons is None or not len(cons):
    st.info("데이터가 없습니다 — python jvm_customs_fetch.py 실행 후 커밋.")
    st.stop()

cons["usd_mn"] = cons["exp_usd_k"] / 1000
cons["year"] = cons["month"].str[:4].astype(int)
cons["region"] = cons["region"].replace({"Latin America": "Others"})
_regc = {"Europe": "#4fb862", "North America": "#eb6834", "Oceania": "#4fb8c9", "Others": "#b5b5b5"}
ms = cons.groupby("month", as_index=False)["usd_mn"].sum().sort_values("month")
ms["yoy"] = ((ms["usd_mn"] / ms["usd_mn"].shift(12) - 1) * 100).replace([float("inf"), -float("inf")], float("nan"))
ms["r12"] = ms["usd_mn"].rolling(12).sum()
_y_cur = int(cons["year"].max()); _y_full = _y_cur - 1
_mmax = int(_lm[5:7]) if _lm else 12
_ytd = cons[cons["year"] == _y_cur]["usd_mn"].sum()
_ytd_prev = cons[(cons["year"] == _y_cur - 1) & (cons["month"].str[5:7].astype(int) <= _mmax)]["usd_mn"].sum()
_full = cons[cons["year"] == _y_full]["usd_mn"].sum()
_full_prev = cons[cons["year"] == _y_full - 1]["usd_mn"].sum()
_last = ms.iloc[-1]
_dal_share = None
if dal is not None and len(dal):
    _d = dal[(dal["hs"] == 392071) & (dal["month"].str[:4] == str(_y_full))]["exp_usd_k"].sum() / 1000
    _dal_share = _d / _full * 100 if _full else None

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"{_lm.replace('-', '.')} 월 수출 (HS 3920.71 전국)", f"${_last['usd_mn']:,.2f}mn",
          f"{_last['yoy']:+.1f}% YoY" if pd.notna(_last["yoy"]) else "", delta_color="normal")
k2.metric(f"{_y_cur}년 1~{_mmax}월 누계", f"${_ytd:,.1f}mn",
          f"{(_ytd / _ytd_prev - 1) * 100:+.1f}% vs 전년 같은 기간" if _ytd_prev else "", delta_color="normal")
k3.metric(f"{_y_full}년 연간", f"${_full:,.1f}mn",
          f"{(_full / _full_prev - 1) * 100:+.1f}% YoY" if _full_prev else "", delta_color="normal")
k4.metric(f"{_y_full}년 대구 달서구 비중", f"{_dal_share:.0f}%" if _dal_share else "n/a",
          "JVM 본사·공장 소재지 → 이 코드는 사실상 JVM", delta_color="off")

st.info("**왜 이 숫자를 보나**: JVM 이 미국 세관에 신고한 선하증권(ImportYeti)에서 ATDPS 파우치 원단의 "
        "품목코드가 **HS 3920.71(재생 셀룰로오스 필름)** 로 확인됨. 한국 전체 3920.71 수출의 약 73% 가 "
        "대구 달서구(JVM 공장)에서 나가고, 행선지 1~3위가 네덜란드(JVM Europe)·캐나다(McKesson)·미국 — "
        "즉 **JVM 소모품 수출의 월별 선행지표**. 기계(ATDPS·MENITH·COUNTMATE 본체)는 HS 8479.89 '기타 기계' 에 "
        "반도체·로봇 장비와 섞여 들어가 **대수나 금액을 따로 셀 수 없음** — 아래 '참고' 로만 둠.")

# ---- 월별 추이
sub("월별 수출 추이 — 최근 3년", "US$mn · 막대 = 권역별 · 주황 선 = 전년 같은 달 대비 % (YoY)")
mr = cons.groupby(["month", "region"], as_index=False)["usd_mn"].sum()
mr36 = mr[mr["month"] >= ms["month"].iloc[-36]].copy()
mr36["date"] = pd.to_datetime(mr36["month"] + "-01")
ms36 = ms.tail(36).copy(); ms36["date"] = pd.to_datetime(ms36["month"] + "-01")
bar_m = alt.Chart(mr36).mark_bar().encode(
    x=alt.X("date:T", title=None, axis=alt.Axis(format="%y %b", labelAngle=0)),
    y=alt.Y("usd_mn:Q", title="월 수출 (US$mn)"),
    color=alt.Color("region:N", title=None, scale=alt.Scale(domain=list(_regc), range=list(_regc.values())),
                    legend=alt.Legend(orient="top")),
    tooltip=[alt.Tooltip("date:T", format="%Y-%m"), "region", alt.Tooltip("usd_mn:Q", format=",.2f")])
line_y = alt.Chart(ms36).mark_line(color="#eb6834", size=2.5, point=True).encode(
    x=alt.X("date:T"), y=alt.Y("yoy:Q", title="YoY (%)"),
    tooltip=[alt.Tooltip("date:T", format="%Y-%m"), alt.Tooltip("yoy:Q", format="+.1f")])
st.altair_chart(alt.layer(bar_m, line_y).resolve_scale(y="independent").properties(height=340),
                use_container_width=True)
st.caption("**읽는법**: 월별은 선적 타이밍 때문에 들쭉날쭉(한 달 0 도 나옴) — 한 달 숫자보다 3개월·12개월 합으로 볼 것. "
           "초록 = 유럽(네덜란드·스페인·벨기에·프랑스 등), 주황 = 북미(캐나다·미국). 확정통계는 약 5주 시차.")

# ---- 12개월 누적 + 연도별
x1, x2 = st.columns(2, gap="large")
with x1:
    sub("12개월 누적 수출 (Rolling 12M)", "US$mn · 추세 보기용")
    r12 = ms.dropna(subset=["r12"]).copy(); r12["date"] = pd.to_datetime(r12["month"] + "-01")
    ch = alt.Chart(r12).mark_area(color="#2a78d6", opacity=0.35, line={"color": "#2a78d6"}).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%Y")),
        y=alt.Y("r12:Q", title="12M 합 (US$mn)"),
        tooltip=[alt.Tooltip("date:T", format="%Y-%m"), alt.Tooltip("r12:Q", format=",.1f")])
    st.altair_chart(ch.properties(height=300), use_container_width=True)
    st.caption("**읽는법**: 2016 $11mn → 2025 $20mn. 꾸준한 우상향 = 설치된 ATDPS 대수가 늘수록 파우치 소비도 늘어나는 구조(반복 매출).")
with x2:
    sub("연도별 수출 — 국가 구성", f"US$mn · {_y_cur}E* = 1~{_mmax}월 연환산")
    top8 = cons[cons["year"] == _y_full].groupby("country_en")["usd_mn"].sum().sort_values(ascending=False).head(8).index
    cy = cons.assign(c=cons["country_en"].where(cons["country_en"].isin(top8), "Others"))
    cy = cy.groupby(["year", "c"], as_index=False)["usd_mn"].sum()
    cy["yr"] = cy["year"].astype(str)
    cy.loc[cy["year"] == _y_cur, "usd_mn"] *= 12 / _mmax
    cy.loc[cy["year"] == _y_cur, "yr"] = f"{_y_cur}E*"
    order = list(top8) + ["Others"]
    bars = alt.Chart(cy).mark_bar().encode(
        x=alt.X("yr:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("usd_mn:Q", title="수출 (US$mn)"),
        color=alt.Color("c:N", title=None, sort=order, scale=alt.Scale(scheme="tableau10"),
                        legend=alt.Legend(orient="top", columns=5)),
        order=alt.Order("usd_mn:Q", sort="descending"),
        tooltip=["yr:O", "c", alt.Tooltip("usd_mn:Q", format=",.2f")])
    tot = cy.groupby("yr", as_index=False)["usd_mn"].sum()
    txt = alt.Chart(tot).mark_text(dy=-8, fontSize=11, color="#c6d0de").encode(
        x=alt.X("yr:O"), y=alt.Y("usd_mn:Q"), text=alt.Text("usd_mn:Q", format=",.1f"))
    st.altair_chart((bars + txt).properties(height=300), use_container_width=True)
    st.caption("**읽는법**: 네덜란드 = JVM Europe 창고(유럽 전체 공급), 캐나다 = McKesson Automation Canada(북미 공급), "
               "스페인 = Ti-Medi. 중국이 보이면 JVM 쑤저우 공장(2026.4~) 또는 타사 물량 — 분리 불가.")

# ---- DART 교차검증 (분기)
sub("DART 교차검증 — 분기", "관세청 3920.71 (US$mn, 왼쪽 축) vs DART 소모품 수출 (KRWbn, 오른쪽 축)")
if dq is not None and len(dq):
    cq = cons.copy()
    cq["quarter"] = cq["month"].str[:4] + "Q" + ((cq["month"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    cq = cq.groupby("quarter", as_index=False)["usd_mn"].sum()
    # 마지막 분기가 꽉 차지 않았으면 제외
    _nm = cons.groupby(cons["month"].str[:4] + "Q" + ((cons["month"].str[5:7].astype(int) - 1) // 3 + 1).astype(str))["month"].nunique()
    cq = cq[cq["quarter"].map(_nm) == 3]
    d2 = dq[["quarter", "consumable", "machine"]].copy()
    d2["cons_bn"] = d2["consumable"] / 1000
    d2["mach_bn"] = d2["machine"] / 1000
    mg = cq.merge(d2, on="quarter", how="outer").sort_values("quarter")
    mg = mg[mg["quarter"] >= "2019Q1"]
    base = alt.Chart(mg).encode(x=alt.X("quarter:O", title=None, axis=alt.Axis(labelAngle=-45)))
    b1 = base.mark_bar(color="#2a78d6", opacity=0.8).encode(
        y=alt.Y("usd_mn:Q", title="관세청 3920.71 (US$mn)"),
        tooltip=["quarter", alt.Tooltip("usd_mn:Q", format=",.2f", title="관세청 US$mn"),
                 alt.Tooltip("cons_bn:Q", format=",.2f", title="DART 소모품 KRWbn")])
    l1 = base.mark_line(color="#e8c15a", size=2.5, point=True).encode(
        y=alt.Y("cons_bn:Q", title="DART 소모품 수출 (KRWbn)"))
    st.altair_chart(alt.layer(b1, l1).resolve_scale(y="independent").properties(height=320),
                    use_container_width=True)
    _q = mg.dropna(subset=["usd_mn", "cons_bn"])
    if len(_q) >= 8:
        _corr = _q["usd_mn"].corr(_q["cons_bn"])
        st.caption(f"**읽는법**: 파랑 막대(관세청 달러)와 금색 선(DART 원화)이 같은 방향이면 이 코드가 JVM 소모품을 잘 잡고 있다는 뜻. "
                   f"2019Q1~ 상관계수 **{_corr:.2f}** (내 계산, 환율 미반영). DART 분기값은 반기·사업보고서 누적에서 앞 분기를 뺀 값(작성자 계산). "
                   "관세청 숫자가 먼저 나오므로(분기 끝 +5주) 다음 분기 소모품 수출의 선행 신호로 쓴다.")

# ---- 국가별 표
sub(f"국가별 수출 — {_y_full}년", "US$mn · YoY · 점유율")
ct = cons[cons["year"].isin([_y_full - 1, _y_full])].groupby(["country_en", "region", "year"])["usd_mn"].sum().unstack("year").fillna(0)
ct = ct.reset_index()
ct["YoY"] = ((ct[_y_full] / ct[_y_full - 1] - 1) * 100).replace([float("inf"), -float("inf")], float("nan"))
ct["점유율"] = ct[_y_full] / ct[_y_full].sum() * 100
ct = ct.sort_values(_y_full, ascending=False).head(12)
ct = ct.rename(columns={"country_en": "국가", "region": "권역", _y_full: f"{_y_full} 수출(US$mn)", _y_full - 1: f"{_y_full - 1} (US$mn)"})
st.dataframe(ct.style.format({f"{_y_full} 수출(US$mn)": "{:,.2f}", f"{_y_full - 1} (US$mn)": "{:,.2f}",
                              "YoY": "{:+.0f}%", "점유율": "{:.0f}%"}),
             use_container_width=True, hide_index=True)

# ---- 참고: 기계 코드
sub("참고 — 기계 코드 HS 8479.89 (ATDPS 본체) — 다른 기계가 섞여 있음", "US$mn · JVM 주요 시장 국가만 · 12개월 합")
if mach is not None and len(mach):
    mach["usd_mn"] = mach["exp_usd_k"] / 1000
    mm = mach[mach["country_kr"].isin(["네덜란드", "캐나다", "스페인", "벨기에", "호주"])]
    mm = mm.groupby(["month", "country_en"], as_index=False)["usd_mn"].sum().sort_values("month")
    mm["r12"] = mm.groupby("country_en")["usd_mn"].transform(lambda s: s.rolling(12).sum())
    mm = mm.dropna(subset=["r12"]); mm["date"] = pd.to_datetime(mm["month"] + "-01")
    ch = alt.Chart(mm).mark_line(size=2).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%Y")),
        y=alt.Y("r12:Q", title="12M 합 (US$mn)"),
        color=alt.Color("country_en:N", title=None, legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("date:T", format="%Y-%m"), "country_en", alt.Tooltip("r12:Q", format=",.1f")])
    st.altair_chart(ch.properties(height=280), use_container_width=True)
    st.caption("**읽는법**: 네덜란드행 8479.89 는 연 $10~17mn 으로 JVM Europe 기계 매출 규모와 비슷하지만, 다른 회사 기계도 "
               "같은 코드로 나가므로 **검증 안 된 참고값**. 캐나다는 2024년 다른 회사 물량이 튀어(연 $76mn) 쓸 수 없음. "
               "미국행은 연 $9억 이상이라 JVM 은 보이지도 않음.")

# ---- 미국 선하증권
sub("미국 통관 선하증권 (ImportYeti, 무료 공개 자료)", "JVM 이 송하인인 해상 선적 · 출처: U.S. Customs and Border Protection")
st.markdown("""
| 항목 | 내용 |
|---|---|
| 송하인 | **Jvm / Jvm Co Ltd** — #121 Hosandong-ro, Dalseo-gu, Daegu |
| 해상 선적 건수 | **131건** (2015.01 ~ **2023.03** 마지막 포착) |
| 주요 수하인 | McKesson Automation Canada 46건 (ATDPS 본체·파우치·리본, 캐나다행 미국 경유) · Parata Systems 35건 (파우치 원단) · Talyst 28건 (ATDPS) · Aesynt 15건 · Omnicell 2건 |
| 품목코드 | 파우치 원단 **3920.71**, ATDPS 본체 **8479.89**, 리본·부품 3926.90 / 6004.10 |
| 한계 | 2017년 이후 선적이 거의 안 잡힘 → 캐나다 직항(캐나다 세관 자료는 비공개)이나 포워더 명의 신고로 추정. **최근 미국행 대수 집계에는 못 씀** |
""")
st.caption("출처: [importyeti.com/supplier/jvm](https://www.importyeti.com/supplier/jvm) (2026-11-11 열람). "
           "Cap IQ Pro 의 Panjiva 도 같은 미국 세관 원자료라 결과가 같을 가능성이 큼 — 확인 필요.")

sub("방법 · 주의")
st.markdown(f"""
- **출처**: 관세청 수출입무역통계 ([tradedata.go.kr](https://tradedata.go.kr)) 품목별·국가별 + 지역별(시도·시군구) 실적, 수리일 기준, 확정통계. 마지막 공표월 **{_lm}**. 수집 {_meta.get('fetched', '')[:16]}.
- **DART**: 사업·반기·분기보고서 '매출실적' 표의 수출 줄 (조제시스템 / 주요소모품 외 / 기타상품). 분기값은 누적 차감 — 작성자 계산.
- **못 하는 것**: 기계 대수. 관세청은 금액·중량만 주고, 기계는 코드가 섞임. 대수는 회사 IR(MENITH 대수) 과 McKesson 발표에 의존.
- **갱신**: `python jvm_customs_fetch.py` (증분) → `python jvm_dart_exports.py` (새 보고서 반영 후) → 커밋·푸시. 월초(확정통계 공표 직후) 한 번.
- 엑셀 짝: `제이브이엠_Analysis template_2026 10_v02h.xlsx` 의 **'수출 트래커 (관세청)'** 시트.
""")
