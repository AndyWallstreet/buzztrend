# -*- coding: utf-8 -*-
"""밸류 스크리너 '현재 멀티플' 을 Cap IQ Pro SPG() 로 직접 받아 screener_data.csv 를 갱신.

Usage:
    python screener_spg_update.py              # 전 종목 (2,774개, 작업용 엑셀, 30~60분)
    python screener_spg_update.py --limit 30   # 시험 (screener_data_test.csv 로 저장)
    python screener_spg_update.py --resume     # 캐시된 청크는 건너뛰고 이어서
    (끝나면: git add data/screener && git commit && git push)

왜 (PM 2026-10-21): v05 비교기업 워크북은 옛 CIQ() 수식이라 9/11 오피스 업데이트 뒤 새로고침이 안 된다
    (#NAME?). SPG() 는 같은 PC 에서 정상이라, 워크북을 거치지 않고 SPG 로 같은 항목을 직접 받는다.
    분류(섹터·산업)는 바뀌지 않으므로 기존 screener_data.csv 의 것을 그대로 쓴다.

항목 (2026-10-21 작업용 엑셀에서 하나씩 확인한 코드만 사용):
    SG       = SP_REV_EST FY2026 / IQ_TOTAL_REV FY-1 − 1  (추정치 없으면 LTM / FY-1 − 1)   ← 글로벌 피어와 동일
    ROIC     = IQ_EBIT LTM × (1 − 유효세율) / (IQ_TOTAL_EQUITY + IQ_TOTAL_DEBT − IQ_CASH_ST_INVEST)
               ※ Cap IQ Pro 에 ROIC 직접 코드가 없어 구성요소로 계산 (Stock Picker 퀄리티 체크와 같은 정의).
                 옛 워크북의 IQ_RETURN_INVESTED_CAPITAL 과 정의가 조금 달라 숫자가 다를 수 있음.
    ROE      = SP_ROE FY0 (%)
    멀티플   = SP_TEV_TOTAL_REV_FWD / SP_TEV_EBIT_FWD / SP_TEV_EBITDA_FWD / SP_PE_FWD "FY2026" (컨센서스 있으면)
               없으면 IQ_TEV_* "LTM" / IQ_PE_EXCL.  PBR = IQ_PBV ÷ 100 (SPG 는 ×100 으로 줌).  EV/FCF = IQ_TEV_UFCF LTM
    시총     = SP_MARKETCAP (십억원) × 1000 → KRWmn (기존 열 단위)  · 주가 = SP_LASTSALEPRICE (KRW)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import win32com.client  # noqa: F401  (pywin32 필요)
from pywintypes import com_error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evfcf_update import get_work_instance  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "screener"
CACHE = OUT / "_spg_cache"
CHUNK = 400

# 열 → (코드, 기간) — 기간 None 이면 두 인자만
F = {
    "rev_fy1": ("IQ_TOTAL_REV", "FY-1"), "rev_ltm": ("IQ_TOTAL_REV", "LTM"), "rev_est": ("SP_REV_EST", "FY2026"),
    "ebit": ("IQ_EBIT", "LTM"), "debt": ("IQ_TOTAL_DEBT", None), "equity": ("IQ_TOTAL_EQUITY", None),
    "cash": ("IQ_CASH_ST_INVEST", None), "tax": ("IQ_EFFECT_TAX_RATE", "LTM"), "roe": ("SP_ROE", "FY0"),
    "evs_l": ("IQ_TEV_TOTAL_REV", "LTM"), "eve_l": ("IQ_TEV_EBIT", "LTM"), "evd_l": ("IQ_TEV_EBITDA", "LTM"),
    "per_l": ("IQ_PE_EXCL", None), "pbr": ("IQ_PBV", None),
    "evs_f": ("SP_TEV_TOTAL_REV_FWD", "FY2026"), "eve_f": ("SP_TEV_EBIT_FWD", "FY2026"),
    "evd_f": ("SP_TEV_EBITDA_FWD", "FY2026"), "per_f": ("SP_PE_FWD", "FY2026"),
    "ev_fcf": ("IQ_TEV_UFCF", "LTM"), "mcap": ("SP_MARKETCAP", None), "price": ("SP_LASTSALEPRICE", None),
}
COLS = list(F)


def retry(fn, tries=60, wait=3, label=""):
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise RuntimeError(f"Excel 이 계속 바쁩니다: {label}: {last}")


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e13 else np.nan


def fetch_chunk(xl, tickers, label):
    """작업용 엑셀에 임시 워크북 하나: A열 티커, B.. 열 수식 → 새로고침 → 값 추출."""
    wb = retry(lambda: xl.Workbooks.Add(), label="새 워크북")
    try:
        ws = wb.Worksheets(1)
        n = len(tickers)
        xl.Calculation = -4135                       # 수식 쓰는 동안 수동 계산
        ws.Range(f"A2:A{n + 1}").Value = tuple((t,) for t in tickers)
        for j, col in enumerate(COLS):
            mn, per = F[col]
            c = ws.Cells(2, 2 + j)
            rng = ws.Range(c, ws.Cells(n + 1, 2 + j))
            rng.FormulaR1C1 = f'=SPG(RC1,"{mn}","{per}")' if per else f'=SPG(RC1,"{mn}")'
        xl.Calculation = -4105
        retry(lambda: ws.Activate(), label="activate")
        retry(lambda: xl.Run("RefreshWorkbook"), label="RefreshWorkbook")
        last_col = ws.Cells(n + 1, 1 + len(COLS))
        deadline = time.time() + 1200
        pend = -1
        while time.time() < deadline:
            time.sleep(15)
            try:
                vals = ws.Range(ws.Cells(2, 2), last_col).Value
            except com_error:
                continue
            pend = sum(1 for row in vals for v in row if v in ("#PEND", "#REFRESH"))
            print(f"  {label}: 남은 셀 {pend:,}", flush=True)
            if pend == 0:
                break
        if pend != 0:
            raise RuntimeError(f"{label}: 새로고침 미완료 ({pend})")
        vals = retry(lambda: ws.Range(ws.Cells(2, 2), last_col).Value, label="extract")
        return [[num(v) for v in row] for row in vals]
    finally:
        try:
            wb.Close(SaveChanges=False)
        except Exception:
            pass


def fill_pbr_from_histdb(tickers, pbr):
    """SPG IQ_PBV 가 'NA' 인 종목(약 8%)은 전 종목 DB(histdb) 의 최신 달 PBR 로 채운다 — 2026-10-21."""
    hp = ROOT / "data" / "histdb" / "multiples.csv.gz"
    if not hp.exists():
        return pbr
    h = pd.read_csv(hp).sort_values("date").groupby("ticker")["pbr"].last()
    fill = pd.Series(tickers.map(h).values, index=pbr.index, dtype="float64")
    out = pbr.astype("float64").where(pbr.notna(), fill.where(fill > 0))
    print(f"  PBR 결측 {int(pbr.isna().sum())}개 중 {int((pbr.isna() & out.notna()).sum())}개를 histdb 로 채움", flush=True)
    return out.round(4)


def main():
    a = sys.argv[1:]
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 0
    resume = "--resume" in a
    base = pd.read_csv(OUT / "screener_data.csv", dtype={"ticker": str}).drop_duplicates("ticker")
    tickers = base["ticker"].tolist()
    if limit:
        tickers = tickers[:limit]
    CACHE.mkdir(exist_ok=True)
    xl = get_work_instance()
    xl.DisplayAlerts = False
    rows = {}
    chunks = [tickers[i:i + CHUNK] for i in range(0, len(tickers), CHUNK)]
    for k, ch in enumerate(chunks):
        cp = CACHE / f"chunk_{k}_{len(ch)}.json"
        if resume and cp.exists() and not limit:
            rows.update(json.loads(cp.read_text(encoding="utf-8")))
            print(f"청크 {k + 1}/{len(chunks)}: 캐시 사용", flush=True)
            continue
        print(f"청크 {k + 1}/{len(chunks)}: {len(ch)}개 × {len(COLS)}항목", flush=True)
        vals = fetch_chunk(xl, ch, f"청크 {k + 1}")
        part = {t: v for t, v in zip(ch, vals)}
        rows.update(part)
        if not limit:
            cp.write_text(json.dumps(part), encoding="utf-8")

    d = pd.DataFrame.from_dict(rows, orient="index", columns=COLS)
    d.index.name = "ticker"
    d = d.reset_index()
    # ---- 파생 지표
    sg = (d["rev_est"] / d["rev_fy1"] - 1).where(d["rev_est"].notna() & (d["rev_fy1"] > 0),
                                                 d["rev_ltm"] / d["rev_fy1"] - 1)
    tax = (d["tax"] / 100).clip(0, 0.4).fillna(0.25)
    ic = d["equity"] + d["debt"].fillna(0) - d["cash"].fillna(0)
    roic = (d["ebit"] * (1 - tax) / ic).where(ic > 0)
    d["roic_sg"] = roic + sg
    d["roe_sg"] = d["roe"] / 100 + sg
    for col, f_, l_ in (("ev_sales", "evs_f", "evs_l"), ("ev_ebit", "eve_f", "eve_l"),
                        ("ev_ebitda", "evd_f", "evd_l"), ("per", "per_f", "per_l")):
        d[col] = d[f_].where(d[f_].notna(), d[l_])
        d[col + "_src"] = np.where(d[f_].notna(), "2026E", np.where(d[l_].notna(), "LTM", ""))
        d.loc[~(d[col] > 0), col] = np.nan
    d["pbr"] = (d["pbr"] / 100).where(d["pbr"] > 0)
    d["pbr"] = fill_pbr_from_histdb(d["ticker"], d["pbr"])
    d.loc[~(d["ev_fcf"] > 0), "ev_fcf"] = np.nan
    d["mcap"] = d["mcap"] * 1000                 # 십억원 → KRWmn
    keep = ["ticker", "company", "sector", "industry_group", "industry", "primary_industry", "sic_industry"]
    out = base[keep].merge(d[["ticker", "roic_sg", "roe_sg", "ev_sales", "ev_ebit", "ev_ebitda", "per", "pbr",
                              "price", "mcap", "ev_fcf", "ev_sales_src", "ev_ebit_src", "ev_ebitda_src", "per_src"]],
                           on="ticker", how="inner")
    out = out[list(base.columns)]
    if limit:
        out.to_csv(OUT / "screener_data_test.csv", index=False, encoding="utf-8-sig")
        print(f"시험 저장: screener_data_test.csv ({len(out)}개)")
        cmp = base.set_index("ticker").loc[out["ticker"], ["roic_sg", "ev_sales", "per", "pbr", "price"]]
        new = out.set_index("ticker")[["roic_sg", "ev_sales", "per", "pbr", "price"]]
        print("옛(8/21) vs 새 — 앞 8개:")
        print(pd.concat([cmp.add_suffix("_old"), new.add_suffix("_new")], axis=1).head(8).round(2).to_string())
        return
    bak = OUT / f"screener_data_{json.loads((OUT / 'meta.json').read_text(encoding='utf-8')).get('as_of', 'old')}.csv"
    if not bak.exists():
        (OUT / "screener_data.csv").replace(bak)
    out.to_csv(OUT / "screener_data.csv", index=False, encoding="utf-8-sig")
    meta = {"as_of": time.strftime("%Y-%m-%d"), "source": "Cap IQ Pro SPG() 직접 추출 (screener_spg_update.py)",
            "basis": "FY2026E consensus, LTM fallback", "n_fwd": int((out["ev_sales_src"] == "2026E").sum()),
            "n_companies": int(len(out)),
            "note": "ROIC = EBIT×(1−유효세율)/(자본+차입−현금) 직접 계산 (Cap IQ Pro 에 ROIC 코드 없음)"}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: screener_data.csv {len(out)}개 · 2026E {meta['n_fwd']}개 · 백업 {bak.name}")
    print(out[["roic_sg", "ev_sales", "ev_ebit", "per", "pbr", "mcap"]].notna().sum().to_dict())


if __name__ == "__main__":
    main()
