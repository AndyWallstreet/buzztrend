# -*- coding: utf-8 -*-
"""실적 시즌 — 커버리지 종목의 분기 실적 발표 캘린더 · 컨센서스 · 발표 후 스코어카드.

데이터 갱신 (로컬에서만 — Streamlit Cloud 는 DART 접속 차단):
    python ~/earnings-season/run_all.py --push
읽는 파일: data/earnings/calendar.csv · consensus.csv · results.csv · meta.json
금액 단위: 원본은 KRWmn(백만원). 화면은 KRWbn(십억원, 1자리) 로 보여 줌.
"""
import datetime as dt
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "earnings"
C_BLUE, C_GOLD, C_RED, C_GREEN, C_GREY = "#2a78d6", "#e8c15a", "#e05252", "#3fb27f", "#8a97aa"

st.set_page_config(page_title="실적 시즌", page_icon="📊", layout="wide")
st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 6px 12px; margin: 0.9rem 0 0.5rem 0; }
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
.lk-card { background:#151d2b; border:1px solid #24304a; border-left:4px solid #2e7de9; border-radius:6px;
           padding:8px 12px; margin-bottom:8px; }
.lk-tag { font-size:0.72rem; padding:1px 7px; border-radius:9px; margin-left:6px; }
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
    return pd.read_csv(p, dtype={"ticker": str, "rcept_no": str, "actual_rcept_no": str, "notice_rcept_no": str})


def get(name):
    return load(name, _stamp(name))


def bn(s):
    """KRWmn → KRWbn (십억원)."""
    return pd.to_numeric(s, errors="coerce") / 1000


cal, con, res = get("calendar.csv"), get("consensus.csv"), get("results.csv")
meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8")) if (DATA / "meta.json").exists() else {}
today = dt.date.today()
season = meta.get("season", "3Q26")

st.title(f"📊 실적 시즌 {season}")
st.caption(f"커버리지 {len(cal) if cal is not None else 0}종목 · 캘린더 {meta.get('calendar_as_of', '—')} · "
           f"컨센서스 {meta.get('consensus_as_of', '—')} · 공시 감시 {meta.get('watch_as_of', '—')} · "
           "발표일 = DART 제출 이력, 컨센서스 = FnGuide(연결), 실제치 = DART 공시")

if cal is None:
    st.error("data/earnings/calendar.csv 가 없습니다 — ~/earnings-season/run_all.py 를 로컬에서 돌리세요.")
    st.stop()

cal["next_date"] = pd.to_datetime(cal["next_date"], errors="coerce").dt.date
cal["D-"] = (pd.to_datetime(cal["next_date"]) - pd.Timestamp(today)).dt.days
up = cal[(cal["status"] != "발표") & cal["next_date"].notna()].sort_values("next_date")

# ── 요약 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric("발표 완료", f"{int((cal['status'] == '발표').sum())} / {len(cal)}",
          f"날짜 확정 {int((cal['date_kind'] == '확정').sum())}건 (예고 공시)", delta_color="off")
if len(up):
    nx = up.iloc[0]
    c2.metric("다음 발표", nx["name"], f"{nx['next_date']} · D-{nx['D-']} · {nx['date_kind']}", delta_color="off")
    wk = up[up["D-"] <= 7]
    c3.metric("이번 주(7일) 발표", f"{len(wk)}개", " · ".join(wk["name"].head(4)), delta_color="off")
if res is not None and len(res):
    vc = res["verdict"].value_counts()
    c4.metric("Beat / In-line / Miss", f"{vc.get('Beat', 0)} / {vc.get('In-line', 0)} / {vc.get('Miss', 0)}",
              f"최근 {res.sort_values('actual_date').iloc[-1]['name']}", delta_color="off")
else:
    c4.metric("Beat / In-line / Miss", "0 / 0 / 0", "아직 발표 없음", delta_color="off")

tabs = st.tabs(["🗓️ 발표 캘린더", "🎯 컨센서스", "✅ 스코어카드"])

# ================================================================ 1) 캘린더
with tabs[0]:
    sub("발표 일정", "동그라미 = 확정(회사 예고 공시) · 마름모 = 추정(과거 3년 제출일 중앙값) · 네모 = 발표됨")
    c = cal.dropna(subset=["next_date"]).copy()
    c["kind"] = c["date_kind"].where(c["status"] != "발표", "발표")
    if con is not None:
        c = c.merge(con[["ticker", "q_op_now", "prior_op", "has_q_cons"]], on="ticker", how="left")
        c["OP cons (KRWbn)"] = bn(c["q_op_now"]).round(1)
        c["OP 3Q25 (KRWbn)"] = bn(c["prior_op"]).round(1)
    _yax = alt.Y("name:N", title=None, sort=alt.SortField("next_date"),
                 axis=alt.Axis(grid=True, gridColor="#2a3852", gridDash=[2, 3], domain=False, ticks=False, labelPadding=8))
    pts = alt.Chart(c).mark_point(size=170, filled=True, opacity=0.95).encode(
        x=alt.X("next_date:T", title=None), y=_yax,
        color=alt.Color("kind:N", title="날짜", scale=alt.Scale(domain=["확정", "추정", "발표"], range=[C_GREEN, C_GREY, C_BLUE]),
                        legend=alt.Legend(orient="top")),
        shape=alt.Shape("kind:N", scale=alt.Scale(domain=["확정", "추정", "발표"], range=["circle", "diamond", "square"]), legend=None),
        tooltip=["next_date", "name", "kind", "status", "prelim_company",
                 alt.Tooltip("OP cons (KRWbn):Q", format=",.1f"), alt.Tooltip("OP 3Q25 (KRWbn):Q", format=",.1f")])
    now = alt.Chart(pd.DataFrame({"d": [today]})).mark_rule(color=C_GOLD, strokeDash=[4, 3]).encode(x="d:T")
    dl = alt.Chart(pd.DataFrame({"d": [dt.date(2026, 11, 16)], "t": ["분기보고서 기한 11/16"]})).mark_rule(color=C_RED, strokeDash=[2, 2]).encode(x="d:T")
    st.altair_chart(alt.layer(now, dl, pts).properties(height=40 + 26 * c["name"].nunique()).configure_view(strokeOpacity=0),
                    use_container_width=True)

    sub("일정표", "가까운 순 · 잠정실적 회사 = 분기보고서보다 먼저 숫자를 냄 · 나머지는 분기보고서(11/16 기한)에서 처음 나옴")
    show = c.sort_values(["next_date", "name"])[["next_date", "D-", "name", "ticker", "kind", "status", "prelim_company",
                                                   "prelim_est", "report_est", "owner", "stage", "ss"]
                                                  + (["OP cons (KRWbn)", "OP 3Q25 (KRWbn)"] if con is not None else [])]
    show = show.rename(columns={"next_date": "다음 발표일", "name": "종목", "ticker": "코드", "kind": "확정/추정", "status": "상태",
                                "prelim_company": "잠정실적", "prelim_est": "잠정 예상일", "report_est": "분기보고서 예상일",
                                "owner": "담당", "stage": "Stage", "ss": "핵심 아이디어"})
    st.dataframe(show, hide_index=True, use_container_width=True, height=min(60 + 35 * len(show), 1100),
                 column_config={"OP cons (KRWbn)": st.column_config.NumberColumn(format="%,.1f"),
                                "OP 3Q25 (KRWbn)": st.column_config.NumberColumn(format="%,.1f"),
                                "D-": st.column_config.NumberColumn(format="%d")})
    for _, x in cal[(cal["date_kind"] == "확정") | (cal["status"] == "발표")].iterrows():
        link = x["actual_url"] if isinstance(x.get("actual_url"), str) and str(x["actual_url"]).startswith("http") else x.get("notice_url", "")
        tag = "발표됨" if x["status"] == "발표" else "날짜 확정"
        col = C_BLUE if x["status"] == "발표" else C_GREEN
        st.markdown(f"<div class='lk-card' style='border-left-color:{col}'><b>{x['next_date']} · {x['name']}</b>"
                    f"<span class='lk-tag' style='background:{col}22;color:{col}'>{tag}</span>"
                    + (f" · <a href='{link}' target='_blank'>DART 공시</a>" if isinstance(link, str) and link.startswith("http") else "")
                    + "</div>", unsafe_allow_html=True)
    st.caption("추정일은 회사가 과거 3년 같은 분기에 공시한 날짜(월·일)의 중앙값입니다. 회사가 '결산실적공시예고' 를 올리면 자동으로 확정으로 바뀝니다.")

# ================================================================ 2) 컨센서스
with tabs[1]:
    if con is None:
        st.info("consensus.csv 가 없습니다.")
    else:
        d = con.copy()
        for k in ("sales", "op", "np"):
            d[f"{k}_cons_bn"] = bn(d[f"q_{k}_now"])
            d[f"{k}_prior_bn"] = bn(d[f"prior_{k}"])
            d[f"{k}_yoy"] = (pd.to_numeric(d[f"q_{k}_now"], errors="coerce") / pd.to_numeric(d[f"prior_{k}"], errors="coerce").where(
                pd.to_numeric(d[f"prior_{k}"], errors="coerce") > 0) - 1)
        d["op_rev_3m"] = pd.to_numeric(d["q_op_now"], errors="coerce") / pd.to_numeric(d["q_op_3m"], errors="coerce").where(
            pd.to_numeric(d["q_op_3m"], errors="coerce") > 0) - 1
        d["op_rev_1m"] = pd.to_numeric(d["q_op_now"], errors="coerce") / pd.to_numeric(d["q_op_1m"], errors="coerce").where(
            pd.to_numeric(d["q_op_1m"], errors="coerce") > 0) - 1
        d["opm_cons"] = pd.to_numeric(d["q_op_now"], errors="coerce") / pd.to_numeric(d["q_sales_now"], errors="coerce")
        d["opm_prior"] = pd.to_numeric(d["prior_op"], errors="coerce") / pd.to_numeric(d["prior_sales"], errors="coerce")
        d["fy_op_rev_3m"] = pd.to_numeric(d["fy_op_now"], errors="coerce") / pd.to_numeric(d["fy_op_3m"], errors="coerce").where(
            pd.to_numeric(d["fy_op_3m"], errors="coerce") > 0) - 1

        sub(f"{season} 영업이익 컨센서스 3개월 변화", "오른쪽(초록) = 지난 3개월 동안 애널리스트들이 숫자를 올림 · 왼쪽(빨강) = 내림")
        r = d.dropna(subset=["op_rev_3m"]).sort_values("op_rev_3m")
        if len(r):
            ch = alt.Chart(r).mark_bar().encode(
                y=alt.Y("name:N", sort="x", title=None), x=alt.X("op_rev_3m:Q", title="OP 컨센 3M 변화", axis=alt.Axis(format="%")),
                color=alt.condition("datum.op_rev_3m >= 0", alt.value(C_GREEN), alt.value(C_RED)),
                tooltip=["name", alt.Tooltip("op_cons_bn", title="3Q26E OP (KRWbn)", format=",.1f"),
                         alt.Tooltip("op_rev_3m", title="3M 변화", format="+.1%"), alt.Tooltip("op_rev_1m", title="1M 변화", format="+.1%"),
                         alt.Tooltip("op_yoy", title="YoY E", format="+.1%")])
            st.altair_chart(ch.properties(height=22 * len(r) + 40), use_container_width=True)
        else:
            st.caption("3개월 전 컨센서스가 있는 종목이 없습니다.")

        sub("컨센서스 표", "단위 KRWbn(십억원) · 컨센 없는 종목은 빈칸 — 전년 동기 YoY 로만 판단")
        t = d[["name", "ticker", "has_q_cons", "sales_prior_bn", "sales_cons_bn", "sales_yoy", "op_prior_bn", "op_cons_bn", "op_yoy",
               "op_rev_1m", "op_rev_3m", "opm_prior", "opm_cons", "np_cons_bn", "fy_op_rev_3m", "tp_now", "per_fwd_now", "n_reports_3m", "last_report"]]
        t = t.rename(columns={"name": "종목", "ticker": "코드", "has_q_cons": "분기 컨센", "sales_prior_bn": "매출 3Q25", "sales_cons_bn": "매출 3Q26E",
                              "sales_yoy": "매출 YoY E", "op_prior_bn": "OP 3Q25", "op_cons_bn": "OP 3Q26E", "op_yoy": "OP YoY E",
                              "op_rev_1m": "OP 1M 변화", "op_rev_3m": "OP 3M 변화", "opm_prior": "OPM 3Q25", "opm_cons": "OPM 3Q26E",
                              "np_cons_bn": "NP 3Q26E", "fy_op_rev_3m": "FY26E OP 3M 변화", "tp_now": "목표주가(KRW)", "per_fwd_now": "Fwd PER",
                              "n_reports_3m": "리포트 3M", "last_report": "최근 리포트"})
        pctcol = {k: st.column_config.NumberColumn(format="%+.1f%%") for k in ["매출 YoY E", "OP YoY E", "OP 1M 변화", "OP 3M 변화", "FY26E OP 3M 변화"]}
        for k in ["OPM 3Q25", "OPM 3Q26E"]:
            pctcol[k] = st.column_config.NumberColumn(format="%.1f%%")
        for k in ["매출 3Q25", "매출 3Q26E", "OP 3Q25", "OP 3Q26E", "NP 3Q26E"]:
            pctcol[k] = st.column_config.NumberColumn(format="%,.1f")
        pctcol["목표주가(KRW)"] = st.column_config.NumberColumn(format="%,.0f")
        pctcol["Fwd PER"] = st.column_config.NumberColumn(format="%.1f")
        for k in ["매출 YoY E", "OP YoY E", "OP 1M 변화", "OP 3M 변화", "FY26E OP 3M 변화", "OPM 3Q25", "OPM 3Q26E"]:
            t[k] = t[k] * 100
        st.dataframe(t.sort_values("OP 3M 변화", ascending=False), hide_index=True, use_container_width=True,
                     height=min(60 + 35 * len(t), 1100), column_config=pctcol)
        st.caption("FnGuide 분기 컨센서스(연결). 억원을 백만원으로 바꾼 뒤 십억원으로 표시. 목표주가는 증권사 평균. "
                   "'리포트 3M' = 최근 92일 증권사 리포트 수 — 0이면 컨센서스가 오래됐을 수 있음.")

# ================================================================ 3) 스코어카드
with tabs[2]:
    if res is None or not len(res):
        st.info(f"아직 {season} 실적을 발표한 종목이 없습니다. 첫 발표: "
                + (f"{up.iloc[0]['name']} {up.iloc[0]['next_date']}" if len(up) else "—"))
    else:
        r = res.copy()
        for k in ("sales", "op", "np"):
            a, c0, p = (pd.to_numeric(r[f"{k}_act"], errors="coerce"), pd.to_numeric(r[f"{k}_cons"], errors="coerce"),
                        pd.to_numeric(r[f"prior_{k}"], errors="coerce"))
            r[f"{k}_surp"] = a / c0.where(c0 > 0) - 1
            r[f"{k}_yoy"] = a / p.where(p > 0) - 1
            r[f"{k}_act_bn"], r[f"{k}_cons_bn"], r[f"{k}_prior_bn"] = bn(r[f"{k}_act"]), bn(r[f"{k}_cons"]), bn(r[f"prior_{k}"])
        sub("영업이익 서프라이즈", "실제 ÷ 컨센 − 1 · +5% 넘으면 Beat, −5% 밑이면 Miss")
        s = r.dropna(subset=["op_surp"]).sort_values("op_surp")
        if len(s):
            ch = alt.Chart(s).mark_bar().encode(
                y=alt.Y("name:N", sort="x", title=None), x=alt.X("op_surp:Q", title="OP 서프라이즈", axis=alt.Axis(format="%")),
                color=alt.condition("datum.op_surp >= 0", alt.value(C_GREEN), alt.value(C_RED)),
                tooltip=["name", "actual_date", "verdict", alt.Tooltip("op_act_bn", title="OP 실제 (KRWbn)", format=",.1f"),
                         alt.Tooltip("op_cons_bn", title="OP 컨센 (KRWbn)", format=",.1f"), alt.Tooltip("op_yoy", title="OP YoY", format="+.1%")])
            st.altair_chart(ch.properties(height=22 * len(s) + 40), use_container_width=True)
        sub("발표 결과", "단위 KRWbn(십억원) · 파싱 OK = N 이면 공시 원문을 열어 숫자를 확인할 것")
        t = r.sort_values("actual_date", ascending=False)[["actual_date", "name", "actual_kind", "verdict", "sales_act_bn", "sales_cons_bn",
                                                            "sales_surp", "sales_yoy", "op_act_bn", "op_cons_bn", "op_surp", "op_yoy",
                                                            "np_act_bn", "np_cons_bn", "np_surp", "parse_ok", "url"]]
        t = t.rename(columns={"actual_date": "발표일", "name": "종목", "actual_kind": "공시", "verdict": "판정", "sales_act_bn": "매출 실제",
                              "sales_cons_bn": "매출 컨센", "sales_surp": "매출 서프", "sales_yoy": "매출 YoY", "op_act_bn": "OP 실제",
                              "op_cons_bn": "OP 컨센", "op_surp": "OP 서프", "op_yoy": "OP YoY", "np_act_bn": "NP 실제", "np_cons_bn": "NP 컨센",
                              "np_surp": "NP 서프", "parse_ok": "파싱 OK", "url": "DART"})
        cfg = {k: st.column_config.NumberColumn(format="%,.1f") for k in ["매출 실제", "매출 컨센", "OP 실제", "OP 컨센", "NP 실제", "NP 컨센"]}
        for k in ["매출 서프", "매출 YoY", "OP 서프", "OP YoY", "NP 서프"]:
            t[k] = t[k] * 100
            cfg[k] = st.column_config.NumberColumn(format="%+.1f%%")
        cfg["DART"] = st.column_config.LinkColumn(display_text="공시")
        st.dataframe(t, hide_index=True, use_container_width=True, height=min(60 + 35 * len(t), 900), column_config=cfg)
        for _, x in r.sort_values("actual_date", ascending=False).iterrows():
            col = {"Beat": C_GREEN, "Miss": C_RED}.get(x["verdict"], C_GREY)
            def f(v):
                return "—" if pd.isna(v) else f"{v:+.1%}"
            st.markdown(f"<div class='lk-card' style='border-left-color:{col}'><b>{x['actual_date']} · {x['name']}</b>"
                        f"<span class='lk-tag' style='background:{col}22;color:{col}'>{x['verdict']}</span>"
                        f"<span class='lk-tag' style='background:#24304a;color:#9ab'>{x['actual_kind']}</span><br>"
                        f"매출 {x['sales_act_bn']:,.1f} vs 컨센 {x['sales_cons_bn']:,.1f} KRWbn ({f(x['sales_surp'])}, YoY {f(x['sales_yoy'])}) · "
                        f"OP {x['op_act_bn']:,.1f} vs 컨센 {x['op_cons_bn']:,.1f} KRWbn ({f(x['op_surp'])}, YoY {f(x['op_yoy'])})"
                        f" · <a href='{x['url']}' target='_blank'>DART</a></div>", unsafe_allow_html=True)
