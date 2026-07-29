# -*- coding: utf-8 -*-
"""밸류 스크리너 데이터 갱신 — 엑셀이 업데이트되면 이 스크립트 한 번만 실행.

Usage:
    python screener_update.py
    (then: git add data/screener && git commit -m "screener data update" && git push)

Reads the Capital IQ comparables workbook (Data sheet, CW:DJ block) and
rewrites data/screener/screener_data.csv + meta.json.
"""
import json
from pathlib import Path

import openpyxl
import pandas as pd

XLSX = (r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Resources"
        r"\02_Industry Analysis\Comparables cap iq_value_AJ editing_v04.xlsx")
OUT = Path(__file__).resolve().parent / "data" / "screener"

COLS = ["ticker", "company", "roic_sg", "roe_sg", "ev_sales", "ev_ebit",
        "ev_ebitda", "per", "pbr", "sector", "industry_group", "industry",
        "primary_industry", "sic_industry"]
NUM_COLS = ["roic_sg", "roe_sg", "ev_sales", "ev_ebit", "ev_ebitda",
            "per", "pbr", "price", "mcap"]


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
    ws = wb["Data"]

    rows = []
    for r in ws.iter_rows(min_row=9, max_col=120):
        if r[100].value is None:          # CW: ticker
            continue
        rec = {name: cell.value for name, cell in zip(COLS, r[100:114])}
        rec["price"] = r[9].value         # J: stock price
        rec["mcap"] = r[16].value         # Q: market cap (KRW mm)
        rows.append(rec)

    df = pd.DataFrame(rows)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["company"].apply(lambda x: isinstance(x, str) and len(x) > 1
                                and "Invalid" not in x)]
    df = df[df["sector"].apply(lambda x: isinstance(x, str) and len(x) > 1)]

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "screener_data.csv", index=False, encoding="utf-8-sig")
    meta = {"as_of": str(ws.cell(row=4, column=10).value)[:10],   # Data!J4
            "source": "Capital IQ comparables workbook",
            "n_companies": len(df)}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"OK — {len(rows)} raw rows, {meta['n_companies']} companies, "
          f"as of {meta['as_of']}")


if __name__ == "__main__":
    main()
