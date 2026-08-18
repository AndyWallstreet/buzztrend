# -*- coding: utf-8 -*-
"""분기 Capex(유형/무형자산 취득) DB — Stock Picker의 Capex 차트용.

Usage:
    python capexdb_update.py [--budget 12000]
    (끝나면: git add data/capexdb && git commit && git push)

Capex는 현금흐름표 항목이라 findb가 쓰는 다중회사 API(주요계정)에 없다.
회사별 전체 재무제표 API(fnlttSinglAcntAll)를 호출해야 해서 비용이 크므로:
- 우선순위: 관심종목 → 시가총액 큰 순
- 하루 호출 예산(--budget) 안에서 수집하고, 어디까지 했는지 state.json에 기록
- 매일 배치가 이어서 돌리면 커버리지가 자동으로 넓어진다
현금흐름표 금액은 연중 누적이라 분기 단독값으로 차분해 저장한다.
"""
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "capexdb"
STATE = OUT / "state.json"
UA = {"User-Agent": "Mozilla/5.0 (lk-terminal capexdb)"}
YEAR_START = 2021
RC = [("11013", 1), ("11012", 2), ("11014", 3), ("11011", 4)]

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass


def dart_key() -> str:
    k = os.environ.get("DART_API_KEY", "")
    if k:
        return k
    sec = BASE / ".streamlit" / "secrets.toml"
    if sec.exists():
        m = re.search(r'DART_API_KEY\s*=\s*"([^"]+)"', sec.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    raise SystemExit("DART_API_KEY가 없습니다")


def corp_map(key: str) -> dict:
    cache = BASE / "data" / "findb" / "corpcode.xml"
    if not cache.exists():
        raise SystemExit("corpcode.xml이 없습니다 — findb_update.py를 먼저 실행하세요")
    xml = cache.read_text(encoding="utf-8")
    out = {}
    for blk in re.finditer(r"<list>(.*?)</list>", xml, re.S):
        b = blk.group(1)
        sc = re.search(r"<stock_code>(\w{6})</stock_code>", b)
        cc = re.search(r"<corp_code>(\d+)</corp_code>", b)
        if sc and cc:
            out[sc.group(1)] = cc.group(1)
    return out


def fetch_one(args):
    """(key, corp, yr, qn, rc) -> (yr, qn, capex_t_cum, capex_i_cum) 또는 None."""
    key, corp, yr, rc, qn = args
    try:
        j = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                         params={"crtfc_key": key, "corp_code": corp,
                                 "bsns_year": str(yr), "reprt_code": rc,
                                 "fs_div": "CFS"},
                         timeout=20, headers=UA).json()
        if j.get("status") != "000":
            j = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                             params={"crtfc_key": key, "corp_code": corp,
                                     "bsns_year": str(yr), "reprt_code": rc,
                                     "fs_div": "OFS"},
                             timeout=20, headers=UA).json()
        if j.get("status") != "000":
            return (yr, qn, None, None)
    except Exception:
        return (yr, qn, None, None)
    ct = ci = None
    for it in j.get("list", []):
        if it.get("sj_div") != "CF":
            continue
        nm = (it.get("account_nm") or "").replace(" ", "")
        s = (it.get("thstrm_amount") or "").replace(",", "")
        try:
            v = abs(int(s))
        except ValueError:
            continue
        if "유형자산" in nm and "취득" in nm and "처분" not in nm:
            ct = (ct or 0) + v
        elif "무형자산" in nm and "취득" in nm and "처분" not in nm:
            ci = (ci or 0) + v
    return (yr, qn, ct, ci)


def main():
    budget = 12000
    for i, a in enumerate(sys.argv):
        if a == "--budget" and i + 1 < len(sys.argv):
            budget = int(sys.argv[i + 1])
    key = dart_key()
    OUT.mkdir(parents=True, exist_ok=True)

    scr = pd.read_csv(BASE / "data" / "screener" / "screener_data.csv")
    scr = scr.drop_duplicates(subset=["ticker"])
    watch = []
    wl = BASE / "data" / "screener" / "history_ciq" / "watchlist.txt"
    if wl.exists():
        watch = [t.strip().upper() for t in wl.read_text(encoding="utf-8").split() if t.strip()]
    by_mcap = scr.sort_values("mcap", ascending=False)["ticker"].tolist()
    order = list(dict.fromkeys(watch + by_mcap))   # 관심종목 먼저, 이후 시총 순

    state = {"done": []}
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    done = set(state.get("done", []))
    cmap = corp_map(key)

    this_year = dt.date.today().year
    years = list(range(YEAR_START, this_year + 1))
    calls_per_ticker = len(years) * len(RC)
    todo = [t for t in order if t not in done and t.lstrip("A") in cmap]
    n_take = max(1, budget // calls_per_ticker)
    batch = todo[:n_take]
    print(f"수집 대상 {len(batch)}개 (남은 {len(todo)}개, 예산 {budget}콜, "
          f"종목당 {calls_per_ticker}콜)")
    if not batch:
        print("모든 종목 수집 완료")
        return

    QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    new_rows = []
    t0 = time.time()
    for bi, t in enumerate(batch):
        corp = cmap[t.lstrip("A")]
        jobs = [(key, corp, yr, rc, qn) for yr in years for rc, qn in RC]
        cum = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            for yr, qn, ct, ci in ex.map(fetch_one, jobs):
                cum[(yr, qn)] = (ct, ci)
        # 누적 -> 분기 단독 (CF는 연중 누적)
        for yr in years:
            prev_t = prev_i = 0
            for qn in (1, 2, 3, 4):
                ct, ci = cum.get((yr, qn), (None, None))
                if ct is None and ci is None:
                    # 이 분기 보고서가 없으면 누적 기준점만 유지
                    continue
                st_t = (ct - prev_t) if ct is not None else None
                st_i = (ci - prev_i) if ci is not None else None
                if ct is not None:
                    prev_t = ct
                if ci is not None:
                    prev_i = ci
                m, d = QEND[qn]
                new_rows.append({"ticker": t, "q": f"{yr}Q{qn}",
                                 "date": dt.date(yr, m, d).isoformat(),
                                 "capex_t": st_t, "capex_i": st_i})
        done.add(t)
        if (bi + 1) % 20 == 0:
            print(f"  {bi + 1}/{len(batch)} ({time.time() - t0:.0f}s)", flush=True)

    new = pd.DataFrame(new_rows)
    db_path = OUT / "capex.csv.gz"
    if db_path.exists() and len(new):
        prev = pd.read_csv(db_path)
        merged = pd.concat([prev[~prev.set_index(["ticker", "q"]).index
                                 .isin(new.set_index(["ticker", "q"]).index)], new])
    else:
        merged = new
    merged = merged.sort_values(["ticker", "q"]).reset_index(drop=True)
    with gzip.open(db_path, "wt", encoding="utf-8", newline="") as f:
        merged.to_csv(f, index=False)
    STATE.write_text(json.dumps({"done": sorted(done),
                                 "updated": dt.date.today().isoformat()},
                                ensure_ascii=False), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(
        {"updated": dt.date.today().isoformat(),
         "tickers": int(merged["ticker"].nunique()), "rows": int(len(merged)),
         "coverage": f"{len(done)}/{len(order)}"}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"OK — 누적 {merged['ticker'].nunique()}개 종목, {len(merged)}행 "
          f"(커버리지 {len(done)}/{len(order)})")
    print("이제: git add data/capexdb && git commit -m 'capexdb update' && git push")


if __name__ == "__main__":
    main()
