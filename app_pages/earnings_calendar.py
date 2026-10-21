# -*- coding: utf-8 -*-
"""실적 시즌 — 진짜 달력 모양(월 그리드)으로 발표 일정 보여주기.

PM 2026-10-21: "Change calendar format like real calendar". 전에는 세로로 종목, 가로로 날짜를 늘어놓은
점 차트였다. 이제 아웃룩처럼 주 = 행, 요일 = 열, 칸 안에 그날 발표 종목을 칩으로 넣는다.

earnings.py 에서 render(c, today, deadline) 로 부른다.
c 열: next_date(date) · name · kind(확정/추정/발표) · status · prelim_company(Y/N) · ticker
       · (있으면) 'OP cons (KRWbn)' · actual_url · notice_url
"""
import calendar
import datetime as dt
import html

import pandas as pd
import streamlit as st

COLOR = {"확정": "#3fb27f", "추정": "#8a97aa", "발표": "#2a78d6"}
DOW = ["일", "월", "화", "수", "목", "금", "토"]

CSS = """
<style>
.ec-wrap { font-family: inherit; }
.ec-grid { display:grid; grid-template-columns: repeat(7, 1fr); gap:3px; }
.ec-dow { text-align:center; font-size:0.78rem; color:#9fb0c8; padding:4px 0 2px 0; }
.ec-cell { background:#121a28; border:1px solid #233048; border-radius:5px; min-height:96px; padding:4px 5px; }
.ec-cell.out { opacity:0.35; }
.ec-cell.wk { background:#0f1521; }
.ec-cell.today { background:#1b3a66; border-color:#2e7de9; box-shadow: inset 0 0 0 1px #2e7de9; }
.ec-cell.dl { border-color:#e05252; }
.ec-day { font-size:0.82rem; color:#c6d2e3; display:flex; justify-content:space-between; margin-bottom:3px; }
.ec-day .n { font-size:0.66rem; color:#e8c15a; }
.ec-chip { display:block; font-size:0.73rem; line-height:1.15; padding:2px 5px; margin:2px 0; border-radius:3px;
           color:#0b1220; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ec-chip a { color:inherit; text-decoration:none; }
.ec-chip.est { background:#2a3852; color:#dde5f0; border-left:3px solid #8a97aa; }
.ec-chip.fix { background:#3fb27f; }
.ec-chip.done { background:#2a78d6; color:#fff; }
.ec-dlmark { font-size:0.66rem; color:#e05252; }
.ec-legend { font-size:0.78rem; color:#9fb0c8; margin:4px 0 8px 2px; }
.ec-legend b { display:inline-block; width:10px; height:10px; border-radius:2px; margin:0 4px 0 10px; vertical-align:middle; }
</style>
"""


def _chip(r):
    kind = r["kind"]
    cls = {"확정": "fix", "발표": "done"}.get(kind, "est")
    name = html.escape(str(r["name"]))
    bits = [f"{kind}", f"상태 {r.get('status', '')}"]
    if r.get("prelim_company") == "Y":
        bits.append("잠정실적 회사")
    op = r.get("OP cons (KRWbn)")
    if op == op and op is not None:
        bits.append(f"OP 컨센 {op:,.1f} KRWbn")
    tip = html.escape(" · ".join(bits))
    link = ""
    for k in ("actual_url", "notice_url"):
        v = r.get(k)
        if isinstance(v, str) and v.startswith("http"):
            link = v
            break
    inner = f"<a href='{html.escape(link)}' target='_blank'>{name}</a>" if link else name
    mark = "●" if kind == "확정" else ("■" if kind == "발표" else "◆")
    return f"<span class='ec-chip {cls}' title='{tip}'>{mark} {inner}</span>"


def month_grid(c, year, month, today, deadline=None):
    """한 달치 HTML. c = next_date 가 있는 행들."""
    cal = calendar.Calendar(firstweekday=6)          # 일요일 시작 (아웃룩과 같게)
    by_day = {}
    for _, r in c.iterrows():
        d = r["next_date"]
        if isinstance(d, dt.date):
            by_day.setdefault(d, []).append(r)
    out = [CSS, "<div class='ec-wrap'><div class='ec-grid'>"]
    for d in DOW:
        out.append(f"<div class='ec-dow'>{d}</div>")
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            cls = ["ec-cell"]
            if d.month != month:
                cls.append("out")
            if d.weekday() >= 5:
                cls.append("wk")
            if d == today:
                cls.append("today")
            if deadline and d == deadline:
                cls.append("dl")
            rows = sorted(by_day.get(d, []), key=lambda r: ({"발표": 0, "확정": 1}.get(r["kind"], 2), str(r["name"])))
            head = f"<div class='ec-day'><span>{d.day}{' 일' if d.day == 1 else ''}</span>"
            head += (f"<span class='n'>{len(rows)}건</span>" if len(rows) >= 2 else "") + "</div>"
            body = "".join(_chip(r) for r in rows)
            if deadline and d == deadline:
                body = "<div class='ec-dlmark'>분기보고서 기한</div>" + body
            out.append(f"<div class='{' '.join(cls)}'>{head}{body}</div>")
    out.append("</div></div>")
    return "".join(out)


def render(c, today, deadline=None):
    c = c.dropna(subset=["next_date"]).copy()
    if not len(c):
        st.info("날짜가 있는 종목이 없습니다.")
        return
    months = sorted({(d.year, d.month) for d in c["next_date"] if isinstance(d, dt.date)} | {(today.year, today.month)})
    labels = [f"{y}년 {m}월" for y, m in months]
    cur = (today.year, today.month)
    idx = months.index(cur) if cur in months else 0
    pick = st.radio("월", labels, index=idx, horizontal=True, key="ec_month", label_visibility="collapsed")
    y, m = months[labels.index(pick)]
    st.markdown("<div class='ec-legend'>오늘 = 파란 칸 · <b style='background:#3fb27f'></b>● 확정(회사 예고 공시) "
                "<b style='background:#8a97aa'></b>◆ 추정(과거 3년 제출일 중앙값) <b style='background:#2a78d6'></b>■ 발표됨 "
                "· 빨간 테두리 = 분기보고서 법정 기한 · 칩에 마우스를 올리면 상태·컨센서스, 클릭하면 DART 공시</div>",
                unsafe_allow_html=True)
    st.markdown(month_grid(c, y, m, today, deadline), unsafe_allow_html=True)
    n_m = int(sum(1 for d in c["next_date"] if isinstance(d, dt.date) and (d.year, d.month) == (y, m)))
    st.caption(f"{pick}: {n_m}개 종목 발표 예정/완료. 다른 달은 위 버튼으로 이동.")
