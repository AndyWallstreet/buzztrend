# -*- coding: utf-8 -*-
"""분기 펀더멘털 DB (구 capexdb) — Stock Picker의 재무 요약/Quick DCF용.

Usage:
    python capexdb_update.py [--budget 12000]
    (끝나면: git add data/capexdb && git commit && git push)

회사별 전체 재무제표 API(fnlttSinglAcntAll)를 호출해 현금흐름표의 Capex뿐
아니라 재무상태표/손익/현금흐름의 핵심 계정 ~15개를 한 번에 뽑는다
(호출 수는 Capex만 뽑던 v1과 동일 — 같은 응답에서 더 많이 파싱할 뿐).
- 우선순위: 관심종목 → 시가총액 큰 순
- 하루 호출 예산(--budget) 안에서 수집, 진행 상황은 state.json의 done2에 기록
  (v1 시절 done 목록은 Capex 2개 열만 있어서 전 종목 재수집 대상)
- 현금흐름표/손익계산서 금액은 연중 누적이라 분기 단독값으로 차분해 저장
- 재무상태표 금액은 시점값이라 그대로 저장

열: capex_t capex_i (v1) + cash stfin ar inv ap ppe intg debt lease (BS)
    + cfo dep div_paid buyback (CF) + cogs sga (IS)
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

# 시점값(BS)과 누적값(CF/IS) 필드
POINT_FIELDS = ["cash", "stfin", "ar", "inv", "ap", "ppe", "intg", "debt", "lease"]
CUM_FIELDS = ["capex_t", "capex_i", "cfo", "dep", "div_paid", "buyback", "cogs", "sga"]

# BS 계정: 부분합/세부항목 이중계상을 피하려고 대표 계정명만 정확 일치로 잡는다
BS_EXACT = {
    "cash": {"현금및현금성자산"},
    "stfin": {"단기금융상품", "단기금융자산", "단기투자자산", "단기투자증권"},
    "ar": {"매출채권", "매출채권및기타채권", "매출채권및기타유동채권", "매출채권및기타수취채권"},
    "inv": {"재고자산"},
    "ap": {"매입채무", "매입채무및기타채무", "매입채무및기타유동채무", "매입채무및기타지급채무"},
    "ppe": {"유형자산"},
    "intg": {"무형자산", "영업권이외의무형자산", "기타무형자산"},
}
SACHAE = {"사채", "전환사채", "신주인수권부사채", "교환사채", "유동성사채", "회사채"}

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


def _num(s):
    s = (s or "").replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _add(d, k, v):
    if v is not None:
        d[k] = (d.get(k) or 0) + v


USDKRW = {2016: 1160, 2017: 1131, 2018: 1100, 2019: 1166, 2020: 1180, 2021: 1144,
          2022: 1292, 2023: 1306, 2024: 1364, 2025: 1420, 2026: 1400}


def _krw(v, ccy, yr):
    """외국적 상장사의 USD 공시 금액을 원화로 (연평균 근사 환율)."""
    if v is None or ccy in ("", "KRW"):
        return v
    return int(v * USDKRW.get(yr, 1400)) if ccy == "USD" else None


def parse_report(items: list, yr: int = 2026) -> dict:
    """전체 재무제표 항목 리스트 -> 필드 dict (CF/IS는 누적 기준, 원화 환산)."""
    d = {}
    for it in items:
        sj = it.get("sj_div")
        nm = (it.get("account_nm") or "").replace(" ", "")
        aid = it.get("account_id") or ""
        ccy = (it.get("currency") or "KRW").strip().upper()
        v = _krw(_num(it.get("thstrm_amount")), ccy, yr)

        if sj == "BS":
            for f, names in BS_EXACT.items():
                if nm in names:
                    _add(d, f, v)
                    break
            else:
                if "리스부채" in nm and "비" != nm[:1]:
                    _add(d, "lease", v)
                elif ("차입금" in nm and "리스" not in nm) or nm in SACHAE \
                        or nm == "유동성장기부채":
                    _add(d, "debt", v)
        elif sj == "CF":
            av = abs(v) if v is not None else None
            if "유형자산" in nm and "취득" in nm and "처분" not in nm:
                _add(d, "capex_t", av)
            elif "무형자산" in nm and "취득" in nm and "처분" not in nm:
                _add(d, "capex_i", av)
            elif aid == "ifrs-full_CashFlowsFromUsedInOperatingActivities" or \
                    ("영업활동" in nm and "현금흐름" in nm and "cfo" not in d):
                if v is not None:
                    d["cfo"] = v
            elif "감가상각" in nm or "무형자산상각" in nm:
                _add(d, "dep", av)
            elif "배당금" in nm and "지급" in nm:
                _add(d, "div_paid", av)
            elif "자기주식" in nm and "취득" in nm:
                _add(d, "buyback", av)
        elif sj in ("IS", "CIS"):
            # 분기보고서 손익은 3개월/누적이 둘 다 오므로 누적(add)을 우선 사용
            cum = _krw(_num(it.get("thstrm_add_amount")), ccy, yr)
            if cum is None:
                cum = v
            if nm == "매출원가":
                _add(d, "cogs", abs(cum) if cum is not None else None)
            elif nm in ("판매비와관리비", "판매비및관리비", "판매관리비"):
                _add(d, "sga", abs(cum) if cum is not None else None)
    return d


def fetch_one(args):
    """(key, corp, yr, rc, qn) -> (yr, qn, dict|None)."""
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
            return (yr, qn, None)
    except Exception:
        return (yr, qn, None)
    return (yr, qn, parse_report(j.get("list", []), int(yr)))


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

    state = {}
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    done = set(state.get("done2", []))   # v2(전 필드) 수집 완료 목록
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
        rep = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            for yr, qn, d in ex.map(fetch_one, jobs):
                rep[(yr, qn)] = d
        # 누적(CF/IS) -> 분기 단독 차분, 시점(BS)은 그대로
        for yr in years:
            prev = {f: 0 for f in CUM_FIELDS}
            for qn in (1, 2, 3, 4):
                d = rep.get((yr, qn))
                if d is None:
                    continue
                row = {"ticker": t, "q": f"{yr}Q{qn}",
                       "date": dt.date(yr, *QEND[qn]).isoformat()}
                for f in CUM_FIELDS:
                    c = d.get(f)
                    if c is None:
                        row[f] = None
                    else:
                        row[f] = c - prev[f]
                        prev[f] = c
                for f in POINT_FIELDS:
                    row[f] = d.get(f)
                new_rows.append(row)
        done.add(t)
        if (bi + 1) % 20 == 0:
            print(f"  {bi + 1}/{len(batch)} ({time.time() - t0:.0f}s)", flush=True)

    cols = ["ticker", "q", "date"] + CUM_FIELDS + POINT_FIELDS
    new = pd.DataFrame(new_rows, columns=cols)
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
    STATE.write_text(json.dumps({"done": state.get("done", []),
                                 "done2": sorted(done),
                                 "updated": dt.date.today().isoformat()},
                                ensure_ascii=False), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(
        {"updated": dt.date.today().isoformat(),
         "tickers": int(merged["ticker"].nunique()), "rows": int(len(merged)),
         "coverage": f"{len(done)}/{len(order)}"}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"OK — 누적 {merged['ticker'].nunique()}개 종목, {len(merged)}행 "
          f"(전 필드 수집 완료 {len(done)}/{len(order)})")
    print("이제: git add data/capexdb && git commit -m 'capexdb update' && git push")


if __name__ == "__main__":
    main()
