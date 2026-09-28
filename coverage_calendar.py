# -*- coding: utf-8 -*-
"""커버리지 이벤트·촉매 캘린더 만들기.

Usage:  python coverage_calendar.py
산출:   data/coverage/catalysts.csv
          date,date_kind,name,ticker,type,title,detail,impact,source,url,confirmed

만드는 방법
  ① 실적 발표(분기·반기·사업보고서) = DART 과거 제출일 패턴으로 예상 (2023~ 같은 분기 제출일의 중앙값)
     → date_kind = "추정(과거 패턴)". 회사가 날짜를 공시하면 손으로 확정일로 바꿀 것.
  ② 그 외 이벤트(신제품·증설 가동·경쟁사·정책) = data/coverage/catalysts_manual.csv 에 손으로 적음
     → 이 스크립트가 ①과 합쳐서 catalysts.csv 를 만든다.
impact: positive / negative / neutral  (negative = 경쟁사 진입 같은 역풍)
"""
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "coverage"
Q_LABEL = {"03": "1분기", "06": "반기", "09": "3분기", "12": "사업보고서(연간)"}


def earnings_rows(cov):
    hist = DATA / "_filing_hist.csv"
    if not hist.exists():
        print("★ _filing_hist.csv 없음 — 먼저 과거 제출일을 받아야 함")
        return []
    h = pd.read_csv(hist, dtype=str)
    h["mmdd"] = h["rcept_dt"].str[4:]
    today = dt.date.today()
    rows = []
    for (name, tkr), g in h.groupby(["name", "ticker"]):
        for pm, lab in Q_LABEL.items():
            gg = g[g["period"].str.endswith("." + pm)]
            if not len(gg):
                continue
            md = sorted(gg["mmdd"])[len(gg) // 2]              # 중앙값 제출일
            # 다음 예정: 올해 것이 아직 안 왔으면 올해, 왔으면 내년
            for yr in (today.year, today.year + 1):
                try:
                    d0 = dt.date(yr + (1 if pm == "12" else 0), int(md[:2]), int(md[2:]))
                except ValueError:
                    continue
                if d0 >= today:
                    break
            if d0 < today:
                continue
            per_y = d0.year - (1 if pm == "12" else 0)
            rows.append({"date": d0.isoformat(), "date_kind": "추정(과거 패턴)", "name": name, "ticker": tkr,
                         "type": "실적", "title": f"{per_y} {lab} 보고서",
                         "detail": f"최근 3년 제출일 {', '.join(sorted(set(gg['mmdd'])))} 의 중앙값으로 추정",
                         "impact": "neutral", "source": "DART 제출 이력", "url": "https://dart.fss.or.kr",
                         "confirmed": "N"})
    return rows


def main():
    cov = pd.read_csv(DATA / "coverage.csv")
    rows = earnings_rows(cov)
    man = DATA / "catalysts_manual.csv"
    if man.exists():
        m = pd.read_csv(man).fillna("")
        rows += m.to_dict("records")
    d = pd.DataFrame(rows)
    d = d[d["date"] >= dt.date.today().isoformat()].sort_values(["date", "name"])
    d.to_csv(DATA / "catalysts.csv", index=False, encoding="utf-8-sig")
    print(f"catalysts.csv: {len(d)}건 · {d['date'].min()} ~ {d['date'].max()}")
    print(d.groupby("type").size().to_string())


if __name__ == "__main__":
    main()
