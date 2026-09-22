# -*- coding: utf-8 -*-
"""YG플러스 — Circle 유통 물량(장) vs 매출(원) → 장당 단가.

Usage:  python ygplus_album_update.py
입력:   data/yg/circle_monthly_all.csv      (circle_dist_update.py 산출, 2011~ 월간 톱100)
        YG플러스 워크북 '3. 매출 및 수주상황' 시트 ① 공시기준 누적 표 (DART 원문)
        data/findb/financials.csv.gz        (A037270 분기 매출·영업이익, 2016~)
산출 (data/ygplus/):
        units_month.csv     month,ygplus_units,market_units,share,albums
        quarterly.csv       분기별 물량·매출·장당 단가
        annual.csv          연도별 같은 표
        top_albums.csv      YG PLUS 유통 앨범 상위 (누적)
        meta.json

용어: '장당 단가' = 그 분기 매출 ÷ 그 분기 YG PLUS 유통 출하량(장).
      유통 수수료율이 아니라 '앨범 1장이 돌 때 회사 매출이 얼마 잡히나'를 보는 지표.
한계: Circle 톱100만 공개 → 순위 밖 물량 누락(단가는 과대평가). 음원·MD 매출은 앨범과
      무관한 부분이 섞여 있음 → 수준보다 '추세'를 볼 것.
"""
import json
import time
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "ygplus"
XLSX = (r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\band chart"
        r"\기업분석 by 클로드_추후 반영\YG플러스_Analysis template_2026 09_v02.xlsx")
DIST = "YG PLUS"
TYPES = ["음악서비스매출", "용역매출", "상ㆍ제품매출", "합 계"]


def circle_units():
    d = pd.read_csv(ROOT / "data" / "yg" / "circle_monthly_all.csv")
    d["dist"] = d["dist"].astype(str).str.strip()
    yg = d[d["dist"].str.upper().str.replace(" ", "") == DIST.replace(" ", "")]
    m = pd.DataFrame({"ygplus_units": yg.groupby("month")["sales"].sum(),
                      "albums": yg.groupby("month")["album"].nunique(),
                      "market_units": d.groupby("month")["sales"].sum()})
    m["share"] = m["ygplus_units"] / m["market_units"]
    m.index.name = "month"
    return d, yg, m.reset_index()


def segment_revenue():
    """워크북 ① 공시기준 누적(DART 원문) → 분기 매출 (단위: 천원 추정, 원문 그대로)."""
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["3. 매출 및 수주상황"]
    R = list(ws.iter_rows(min_row=6, max_row=24, max_col=45, values_only=True))
    years = {i: int(v) for i, v in enumerate(R[0]) if isinstance(v, (int, float))}
    rows = []
    cur = None
    for r in R[2:]:
        if r[0]:
            cur = str(r[0]).strip()
        if str(r[1]).strip() != "합계" or cur not in TYPES:
            continue
        for c0, y in years.items():                      # c0=1Q누적, +1 반기, +2 3Q, +3 연간
            cum = [r[c0 + k] if isinstance(r[c0 + k], (int, float)) else None for k in range(4)]
            prev = 0.0
            for k, v in enumerate(cum):
                if v is None:
                    prev = None                          # 누적이 비면 그 다음 분기도 못 구함
                    continue
                if prev is None:
                    prev = v                             # 앞이 비었으면 이 분기는 못 나눔 → 건너뜀
                    continue
                rows.append({"type": cur, "q": f"{y}Q{k + 1}", "rev": v - prev})
                prev = v
    t = pd.DataFrame(rows).pivot_table(index="q", columns="type", values="rev", aggfunc="first")
    return t.rename(columns={"합 계": "합계"})


def findb_rev():
    f = pd.read_csv(ROOT / "data" / "findb" / "financials.csv.gz")
    g = f[(f["ticker"] == "A037270") & (f["fs"] == "CFS")].copy()
    g["rev_krwmn"] = g["rev"] / 1e6
    g["ebit_krwmn"] = g["ebit"] / 1e6
    return g.set_index("q")[["rev_krwmn", "ebit_krwmn"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d, yg, m = circle_units()
    m.to_csv(OUT / "units_month.csv", index=False, encoding="utf-8-sig")

    m["y"] = m["month"].str[:4].astype(int)
    m["q"] = m["y"].astype(str) + "Q" + ((m["month"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    qu = m.groupby("q").agg(units=("ygplus_units", "sum"), market=("market_units", "sum"),
                            albums=("albums", "max"), n_month=("month", "count"))
    qu["share"] = qu["units"] / qu["market"]

    seg = segment_revenue()                                # 원문 단위(천원)
    fin = findb_rev()                                      # KRWmn
    t = qu.join(seg / 1000.0, how="outer").join(fin, how="outer")   # 천원 → 백만원
    t.index.name = "q"
    t = t[t.index.astype(str).str[:4].astype(int) >= 2011]
    # 매출이 없으면 findb 총매출로 보완
    if "합계" in t.columns:
        t["합계"] = t["합계"].fillna(t["rev_krwmn"])
    for c in ("음악서비스매출", "용역매출", "상ㆍ제품매출", "합계"):
        if c in t.columns:
            t[f"{c}_원장"] = np.where(t["units"] > 0, t[c] * 1e6 / t["units"], np.nan)
    t["n_month"] = t["n_month"].fillna(0).astype(int)
    t = t.reset_index()
    t.to_csv(OUT / "quarterly.csv", index=False, encoding="utf-8-sig")

    a = t.copy()
    a["year"] = a["q"].str[:4].astype(int)
    full = a.groupby("year")["n_month"].sum()
    ann = a.groupby("year").agg(units=("units", "sum"), market=("market", "sum"),
                                **{c: (c, "sum") for c in ("음악서비스매출", "용역매출", "상ㆍ제품매출", "합계") if c in a.columns})
    ann["n_month"] = full
    ann["share"] = ann["units"] / ann["market"]
    for c in ("음악서비스매출", "용역매출", "상ㆍ제품매출", "합계"):
        if c in ann.columns:
            ann.loc[ann[c] == 0, c] = np.nan
            ann[f"{c}_원장"] = np.where(ann["units"] > 0, ann[c] * 1e6 / ann["units"], np.nan)
    ann.reset_index().to_csv(OUT / "annual.csv", index=False, encoding="utf-8-sig")

    top = (yg.groupby(["artist", "album"]).agg(units=("sales", "sum"), first=("month", "min"),
                                               last=("month", "max"), months=("month", "nunique"))
           .sort_values("units", ascending=False).reset_index())
    top.head(300).to_csv(OUT / "top_albums.csv", index=False, encoding="utf-8-sig")

    (OUT / "meta.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%d"),
        "circle_months": [m["month"].min(), m["month"].max()],
        "revenue_quarters": [str(seg.index.min()), str(seg.index.max())],
        "unit_note": "Circle 월간 앨범차트 톱100 · 출하량−반품량 · 유통사 'YG PLUS' 행 합계",
        "rev_note": "DART 사업보고서 매출유형별(원문 천원) → 백만원 환산. 음악서비스 = 음원유통+네이버 플랫폼 수익배분, 음반유통 수수료는 용역매출.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"units {m['month'].min()}~{m['month'].max()} · 분기 {len(t)}행 · 상위앨범 {len(top)}개")
    print(t.tail(10)[["q", "units", "share", "음악서비스매출", "음악서비스매출_원장", "용역매출_원장", "합계_원장"]].round(2).to_string())


if __name__ == "__main__":
    main()
