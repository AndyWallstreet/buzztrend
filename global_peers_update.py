# -*- coding: utf-8 -*-
"""글로벌 피어 (MSCI ACWI 구성종목) — Cap IQ에서 한국 스크린과 같은 지표를 뽑는다.

Usage:
    python global_peers_update.py            # 전체 (약 2,200종목, 40~90분)
    python global_peers_update.py --limit 60 # 시험용
    (then: git add data/screener/global_data.csv data/screener/global_meta.json && commit && push)

입력:  data/screener/global/acwi_members_raw.csv  (SPDR MSCI ACWI 보유종목 + OpenFIGI 티커, figi_map.py 산출)
       data/screener/global/nse_equity_list.csv   (인도 NSE 심볼 ↔ ISIN)
       data/screener/global/extra_peers.csv       (선택: ciq_id 열 — MSCI 밖의 피어를 직접 추가, 예: BIT:ICOS)
산출:  data/screener/global_data.csv  (screener_data.csv 와 같은 컬럼 + country, region='Global')

지표는 한국 워크북(Comparables cap iq) Data 시트 수식과 동일:
  SG = SP_REV_EST FY2026 / IQ_TOTAL_REV FY-1 − 1 (추정치 없으면 LTM/FY-1 − 1)
  ROIC+SG = IQ_RETURN_INVESTED_CAPITAL(LTM)/100 + SG ;  ROE+SG = IQ_ROE(FY0)/100 + SG
  멀티플 = CY2026 포워드(IQ_TEV_TOTAL_REV_FWD 등), 없으면 LTM. PBR = LTM.
Excel 은 애드인이 로드된 '작업용 인스턴스'(evfcf_update.get_work_instance)만 쓴다 — 사용자 엑셀은 안 건드림.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
G = ROOT / "data" / "screener" / "global"
OUT = ROOT / "data" / "screener" / "global_data.csv"

# Bloomberg 거래소 코드(국가 합성) → Cap IQ 거래소 접두어
EX = {"JP": "TSE", "HK": "SEHK", "TT": "TWSE", "LN": "LSE", "FP": "ENXTPA", "GY": "XTRA", "GR": "XTRA",
      "CN": "TSX", "AU": "ASX", "BZ": "BOVESPA", "SW": "SWX", "NA": "ENXTAM", "SS": "OM", "DC": "CPSE",
      "SM": "BME", "IM": "BIT", "AB": "SASE", "SJ": "JSE", "MM": "BMV", "IJ": "IDX", "TB": "SET",
      "MK": "KLSE", "SP": "SGX", "BB": "ENXTBR", "FH": "HLSE", "NO": "OB", "ID": "ISE", "IT": "TASE",
      "PW": "WSE", "TI": "IBSE", "PM": "PSE", "NZ": "NZSE", "AV": "WBAG", "PL": "ENXTLS", "GA": "ATSE",
      "CI": "SNSE", "HB": "BUSE", "CP": "SEP", "UH": "DFM", "QD": "DSM", "KK": "KWSE", "CB": "BVC",
      "PE": "BVL", "EY": "CASE"}


def ciq_id(r, nse):
    t, ex, isin = r.get("bb_ticker"), r.get("bb_exch"), r["ISIN"]
    if isinstance(isin, str) and isin.startswith("INE") and isin in nse:
        return "NSEI:" + nse[isin]
    if not isinstance(t, str) or not t:
        return None
    t = t.replace("/", ".").strip()
    if ex in ("US", "UN", "UW", "UQ", "UR", "UA", "UP"):
        return t                               # 미국은 접두어 없이도 CIQ가 풀어줌 (→ IQ_COMPANY_TICKER 로 확정)
    if ex in ("CH", "CS", "CG", "C1", "C2"):
        return ("SHSE:" if t[:1] in "69" else "SZSE:") + t
    if ex in EX:
        return f"{EX[ex]}:{t}"
    return None


def wait_refresh(xl, ws, r0, r1, c0, c1, label, max_min=60):
    """RefreshWorkbook 을 반복 호출하며 #PEND / Refresh 문구가 사라질 때까지 기다림."""
    t0 = time.time()
    while True:
        try:
            xl.Run("RefreshWorkbook")
        except Exception:
            pass
        time.sleep(20)
        try:
            vals = ws.Range(ws.Cells(r0, c0), ws.Cells(r1, c1)).Value
        except Exception:
            continue
        pend = sum(1 for row in vals for v in row if isinstance(v, str) and ("#PEND" in v or "Refresh" in v or "Requesting" in v))
        print(f"  [{label}] 대기 중 셀 {pend} · {int(time.time() - t0)}s", flush=True)
        if pend == 0 or time.time() - t0 > max_min * 60:
            return vals


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    mp = G / "acwi_members_raw.csv"
    m = pd.read_csv(mp) if mp.exists() else pd.DataFrame(columns=["ISIN", "bb_ticker", "bb_exch", "Security Name", "Trade Country Name"])
    nse = {}
    if (G / "nse_equity_list.csv").exists():
        n = pd.read_csv(G / "nse_equity_list.csv")
        n.columns = [c.strip() for c in n.columns]
        nse = dict(zip(n["ISIN NUMBER"].str.strip(), n["SYMBOL"].str.strip()))
    m["ciq_in"] = [ciq_id(r, nse) for _, r in m.iterrows()]
    ids = m[m["ciq_in"].notna()].drop_duplicates("ciq_in")
    extra = G / "extra_peers.csv"
    if extra.exists():
        e = pd.read_csv(extra)
        e = e[~e["ciq_id"].isin(ids["ciq_in"])]
        ids = pd.concat([ids, pd.DataFrame({"ciq_in": e["ciq_id"], "Security Name": e.get("name", ""),
                                            "Trade Country Name": e.get("country", "")})], ignore_index=True)
    if "--only-extra" in sys.argv:          # 시험용: extra_peers.csv 만
        ids = ids[ids["ciq_in"].isin(pd.read_csv(extra)["ciq_id"])]
        limit = limit or len(ids)
    if limit:
        ids = ids.head(limit)
    print(f"구성종목 {len(m)} → Cap IQ 식별자 {len(ids)}개")

    from evfcf_update import get_work_instance
    from history_ciq_update import ensure_snl_xla
    xl = get_work_instance()
    ensure_snl_xla(xl)
    wb = xl.Workbooks.Add()
    ws = wb.Worksheets(1)
    xl.Calculation = -4135          # 수식 쓰는 동안 수동 계산
    n = len(ids)
    r0, r1 = 2, n + 1
    ws.Range(ws.Cells(r0, 1), ws.Cells(r1, 1)).Value = [[v] for v in ids["ciq_in"]]
    # ---- 1차: 식별자 확정 + 분류 (CIQ 함수만)
    P1 = ["IQ_COMPANY_TICKER", "IQ_COMPANY_NAME", "IQ_COUNTRY_NAME", "IQ_INDUSTRY_SECTOR", "IQ_INDUSTRY_GROUP",
          "IQ_INDUSTRY", "IQ_PRIMARY_INDUSTRY", "IQ_PRIMARY_SIC_INDUSTRY"]
    for j, mn in enumerate(P1):
        ws.Range(ws.Cells(r0, 2 + j), ws.Cells(r1, 2 + j)).Formula = f'=CIQ($A{r0},"{mn}")'
    xl.Calculation = -4105
    wb.Activate()
    v1 = wait_refresh(xl, ws, r0, r1, 2, 1 + len(P1), "1차 식별·분류", 40)
    p1 = pd.DataFrame(v1, columns=["ticker", "company", "country", "sector", "industry_group", "industry",
                                   "primary_industry", "sic_industry"])
    ok = p1["ticker"].astype(str).str.contains(":") & ~p1["ticker"].astype(str).str.contains("Invalid")
    print(f"  식별 성공 {int(ok.sum())} / {n}")
    ws.Range(ws.Cells(r0, 2), ws.Cells(r1, 1 + len(P1))).Value = v1     # 값으로 고정 (재조회 방지)

    # ---- 2차: 지표 (한국 Data 시트와 같은 수식). K열 = 확정 티커(B)
    F = {  # col: formula (row r0 기준, 아래로 채움)
        11: '=SPG($B{r},"IQ_TOTAL_REV","FY-1")',
        12: '=SPG($B{r},"IQ_TOTAL_REV","LTM")',
        13: '=SPG($B{r},"SP_REV_EST","FY2026")',
        14: '=CIQ($B{r},"IQ_RETURN_INVESTED_CAPITAL","IQ_LTM")',
        15: '=SPG($B{r},"IQ_ROE","FY0")',
        16: '=CIQ($B{r},"IQ_TEV_TOTAL_REV",IQ_LTM)', 17: '=CIQ($B{r},"IQ_TEV_EBIT",IQ_LTM)',
        18: '=CIQ($B{r},"IQ_TEV_EBITDA",IQ_LTM)', 19: '=CIQ($B{r},"IQ_PE_EXCL",IQ_LTM)',
        20: '=CIQ($B{r},"IQ_PBV",IQ_LTM)',
        21: '=CIQ($B{r},"IQ_TEV_TOTAL_REV_FWD","CY2026")', 22: '=CIQ($B{r},"IQ_TEV_EBIT_FWD","CY2026")',
        23: '=CIQ($B{r},"IQ_TEV_EBITDA_FWD","CY2026")', 24: '=CIQ($B{r},"IQ_PE_EXCL_FWD","CY2026")',
        25: '=CIQ($B{r},"IQ_TEV_UFCF",IQ_LTM)',
    }
    xl.Calculation = -4135
    for c, f in F.items():
        ws.Range(ws.Cells(r0, c), ws.Cells(r1, c)).Formula = f.format(r=r0)
    xl.Calculation = -4105
    v2 = wait_refresh(xl, ws, r0, r1, 11, 25, "2차 지표", 120)
    wb.Close(SaveChanges=False)

    num = lambda x: x if isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e12 else np.nan
    d = pd.DataFrame([[num(x) for x in row] for row in v2],
                     columns=["rev_fy1", "rev_ltm", "rev_est", "roic", "roe", "evs_l", "eve_l", "evd_l", "per_l", "pbr",
                              "evs_f", "eve_f", "evd_f", "per_f", "ev_fcf"])
    out = pd.concat([p1, d], axis=1)[ok.values].copy()
    out["in_id"] = ids["ciq_in"].values[ok.values]
    sg = (out["rev_est"] / out["rev_fy1"] - 1).where(out["rev_est"].notna() & (out["rev_fy1"] > 0),
                                                     out["rev_ltm"] / out["rev_fy1"] - 1)
    out["roic_sg"] = out["roic"] / 100 + sg
    out["roe_sg"] = out["roe"] / 100 + sg
    for col, f_, l_ in (("ev_sales", "evs_f", "evs_l"), ("ev_ebit", "eve_f", "eve_l"),
                        ("ev_ebitda", "evd_f", "evd_l"), ("per", "per_f", "per_l")):
        out[col] = out[f_].where(out[f_].notna(), out[l_])
        out[col + "_src"] = np.where(out[f_].notna(), "2026E", np.where(out[l_].notna(), "LTM", None))
        out.loc[~(out[col] > 0), col] = np.nan
    out.loc[~(out["pbr"] > 0), "pbr"] = np.nan
    out["region"] = "Global"
    cols = ["ticker", "company", "roic_sg", "roe_sg", "ev_sales", "ev_ebit", "ev_ebitda", "per", "pbr", "sector",
            "industry_group", "industry", "primary_industry", "sic_industry", "ev_fcf", "ev_sales_src", "ev_ebit_src",
            "ev_ebitda_src", "per_src", "country", "region"]
    out = out[cols].drop_duplicates("ticker")
    out = out[out["country"] != "South Korea"]
    if limit:
        OUTP = OUT.with_name("global_data_test.csv")
    else:
        OUTP = OUT
    out.to_csv(OUTP, index=False, encoding="utf-8-sig")
    (OUT.with_name("global_meta.json")).write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%d"), "universe": "MSCI ACWI (SPDR MSCI ACWI UCITS ETF 보유종목 기준, 한국 제외)",
        "n_companies": int(len(out)), "n_fwd": int((out["ev_sales_src"] == "2026E").sum()),
        "n_input": int(n), "n_resolved": int(ok.sum())}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUTP.name} — {len(out)}개사 (2026E 멀티플 {int((out['ev_sales_src'] == '2026E').sum())}개)")
    print(out[["roic_sg", "ev_sales", "ev_ebit", "per", "pbr"]].notna().sum().to_dict())


if __name__ == "__main__":
    main()
