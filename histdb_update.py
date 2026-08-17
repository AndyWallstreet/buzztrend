# -*- coding: utf-8 -*-
"""전 종목 과거 멀티플 DB(histdb) 구축 — 월별 EV/Sales·EV/EBIT·PER·PBR (TTM).

Usage:
    python histdb_update.py            # 전 종목 재계산 (로컬, 15~20분)
    (끝나면: git add data/histdb && git commit && git push)

클라우드 서버는 DART가 차단해 즉석 계산이 불가하므로, 로컬에서 미리 계산해
data/histdb/multiples.csv.gz 로 배포한다. 재료: 네이버 주간 종가(월말 추출) +
findb 분기 재무(TTM 합산) + DART 주식수/순부채(최신값 고정 근사).
EV/EBITDA·EV/FCF는 공개 데이터로 못 만들어 CIQ 관심종목에서만 제공.
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

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "app_pages"))

# DART 키를 환경변수로 먼저 심어 history_fetch가 읽게 한다
_sec = BASE / ".streamlit" / "secrets.toml"
if "DART_API_KEY" not in os.environ and _sec.exists():
    m = re.search(r'DART_API_KEY\s*=\s*"([^"]+)"', _sec.read_text(encoding="utf-8"))
    if m:
        os.environ["DART_API_KEY"] = m.group(1)

import history_fetch as hf  # noqa: E402

OUT = BASE / "data" / "histdb"
LAG_DAYS = 45


def month_end_prices(px):
    """주간 종가 목록 [(date, close)] -> 월별 마지막 종가 [(date, close)]."""
    by_month = {}
    for d, c in px:
        by_month[(d.year, d.month)] = (d, c)
    return [by_month[k] for k in sorted(by_month)]


def one_ticker(args):
    t, corp, key, fin = args
    t6 = t.lstrip("A")
    try:
        px = hf._prices(t6)
        if len(px) < 12:
            return None
    except Exception:
        return None
    shares = nd = None
    try:
        shares = hf._shares(corp, key)
    except Exception:
        pass
    try:
        nd = hf._netdebt(corp, key)
    except Exception:
        nd = 0

    # findb 분기(단독) -> TTM
    fin = fin.sort_values("date")
    ttm = []
    rows = fin.to_dict("records")
    for i in range(3, len(rows)):
        w = rows[i - 3:i + 1]
        if any(pd.isna(x[k]) for x in w for k in ("rev", "ebit", "ni")):
            continue
        ttm.append({"eff": rows[i]["date"] + dt.timedelta(days=LAG_DAYS),
                    "rev": sum(x["rev"] for x in w),
                    "ebit": sum(x["ebit"] for x in w),
                    "ni": sum(x["ni"] for x in w),
                    "eq": rows[i]["eq"]})
    if not ttm or shares is None:
        return None

    # 주식수 단위 오기재 방어
    last_eq = next((x["eq"] for x in reversed(ttm) if pd.notna(x["eq"])), None)
    if last_eq:
        while (px[-1][1] / (last_eq / shares)) > 100:
            shares //= 1000

    recs = []
    for d, close in month_end_prices(px):
        cur = None
        for x in ttm:
            if x["eff"] <= d:
                cur = x
            else:
                break
        if cur is None:
            continue
        ev = close * shares + (nd or 0)
        recs.append({
            "ticker": t, "date": d.isoformat(), "px": close,
            "evs": round(ev / cur["rev"], 4) if cur["rev"] and cur["rev"] > 0 else None,
            "eve": round(ev / cur["ebit"], 4) if cur["ebit"] and cur["ebit"] > 0 else None,
            "per": round(close / (cur["ni"] / shares), 4) if cur["ni"] and cur["ni"] > 0 else None,
            "pbr": round(close / (cur["eq"] / shares), 4)
                   if pd.notna(cur["eq"]) and cur["eq"] > 0 else None,
        })
    return recs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        raise SystemExit("DART_API_KEY가 없습니다")
    findb = pd.read_csv(BASE / "data" / "findb" / "financials.csv.gz")
    findb["date"] = pd.to_datetime(findb["date"]).dt.date
    cmap = hf._corp_map()

    groups = {t: g for t, g in findb.groupby("ticker")}
    jobs = [(t, cmap[t.lstrip("A")], key, g) for t, g in groups.items()
            if t.lstrip("A") in cmap]
    print(f"대상 {len(jobs)}개 종목 — 주가/주식수/순부채 수집 + 멀티플 계산...")

    all_recs = []
    done = ok = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(one_ticker, jobs):
            done += 1
            if r:
                ok += 1
                all_recs.extend(r)
            if done % 200 == 0:
                print(f"  {done}/{len(jobs)} (성공 {ok}, {time.time()-t0:.0f}s)", flush=True)

    db = pd.DataFrame(all_recs).sort_values(["ticker", "date"]).reset_index(drop=True)
    with gzip.open(OUT / "multiples.csv.gz", "wt", encoding="utf-8", newline="") as f:
        db.to_csv(f, index=False)
    (OUT / "meta.json").write_text(json.dumps(
        {"updated": dt.date.today().isoformat(),
         "tickers": int(db["ticker"].nunique()), "rows": int(len(db)),
         "freq": "monthly", "basis": "TTM (Naver+DART, 순부채·주식수 최신값 고정)"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK — 종목 {db['ticker'].nunique()}개, {len(db)}행 → {OUT / 'multiples.csv.gz'}")
    print("이제: git add data/histdb && git commit -m 'histdb update' && git push")


if __name__ == "__main__":
    main()
