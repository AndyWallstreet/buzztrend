# -*- coding: utf-8 -*-
"""전 종목 분기 재무 데이터베이스(findb) 구축·갱신 — LK Terminal 2단계.

Usage:
    python findb_update.py              # 최근 2개 연도만 갱신 (주간 배치용, ~500콜)
    python findb_update.py --backfill   # 2016년부터 전체 백필 (~2,400콜, 5~10분)
    (끝나면: git add data/findb && git commit && git push)

DART '다중회사 주요계정'(fnlttMultiAcnt) API로 한 번에 여러 회사를 받아서
호출 수를 줄인다 (회사별 개별 호출이면 12만 콜 → 이 방식이면 ~2,400콜).
연결(CFS) 우선, 없으면 별도(OFS). 누적 분기를 단독 분기로 환산해
data/findb/financials.csv.gz 로 저장한다. 사이트(Stock Picker)가 이 파일을
먼저 읽고, 없는 종목만 즉석 DART 조회로 폴백한다.
"""
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "findb"
CSV = BASE / "data" / "screener" / "screener_data.csv"
UA = {"User-Agent": "Mozilla/5.0 (lk-terminal findb)"}
FUND_START = 2016
# 외국적 상장사(950xxx 등)는 USD로 공시하므로 원화로 환산한다 — 연평균 근사 (원/달러)
USDKRW = {2016: 1160, 2017: 1131, 2018: 1100, 2019: 1166, 2020: 1180, 2021: 1144,
          2022: 1292, 2023: 1306, 2024: 1364, 2025: 1420, 2026: 1400}


def to_krw(v, ccy, yr):
    """DART 금액을 원화로. KRW면 그대로, USD면 연평균 환율 적용, 그 외 통화는 None."""
    if v is None or ccy in (None, "", "KRW"):
        return v
    if ccy == "USD":
        return int(v * USDKRW.get(int(yr), 1400))
    return None
BATCH = 50          # fnlttMultiAcnt 한 번에 보낼 corp_code 수
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
    raise SystemExit("DART_API_KEY가 없습니다 (.streamlit/secrets.toml 또는 환경변수)")


def corp_map(key: str) -> dict:
    """6자리 종목코드 -> corp_code (상장사만)."""
    cache = OUT / "corpcode.xml"
    OUT.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or time.time() - cache.stat().st_mtime > 30 * 86400:
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": key}, timeout=120, headers=UA)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        cache.write_bytes(z.read(z.namelist()[0]))
    xml = cache.read_text(encoding="utf-8")
    out = {}
    for blk in re.finditer(r"<list>(.*?)</list>", xml, re.S):
        b = blk.group(1)
        sc = re.search(r"<stock_code>(\w{6})</stock_code>", b)
        cc = re.search(r"<corp_code>(\d+)</corp_code>", b)
        if sc and cc:
            out[sc.group(1)] = cc.group(1)
    return out


def fetch_batch(args):
    """(key, corp_codes, yr, rc) -> corp_code별 {계정: (값, fs_div)} 목록."""
    key, codes, yr, rc = args
    try:
        j = requests.get("https://opendart.fss.or.kr/api/fnlttMultiAcnt.json",
                         params={"crtfc_key": key, "corp_code": ",".join(codes),
                                 "bsns_year": yr, "reprt_code": rc},
                         timeout=30, headers=UA).json()
    except Exception:
        return {}
    if j.get("status") != "000":
        return {}
    out = {}
    for it in j.get("list", []):
        cc = it.get("corp_code")
        nm = (it.get("account_nm") or "").strip()
        if nm.startswith("당기순이익"):
            nm = "당기순이익"
        if nm not in ("매출액", "영업이익", "당기순이익", "자본총계"):
            continue
        s = (it.get("thstrm_amount") or "").replace(",", "")
        try:
            v = int(s)
        except ValueError:
            continue
        fs = it.get("fs_div", "OFS")
        ccy = (it.get("currency") or "KRW").strip().upper()
        v = to_krw(v, ccy, yr)
        if v is None:
            continue
        rec = out.setdefault(cc, {})
        # 연결(CFS) 우선 — 이미 CFS 값이 있으면 OFS로 덮지 않는다
        if nm not in rec or (fs == "CFS" and rec[nm][1] != "CFS"):
            rec[nm] = (v, fs)
    return {(cc, yr, rc): rec for cc, rec in out.items()}


def main():
    backfill = "--backfill" in sys.argv
    key = dart_key()
    tickers = pd.read_csv(CSV)["ticker"].drop_duplicates().str.lstrip("A").tolist()
    cmap = corp_map(key)
    corps = {t: cmap[t] for t in tickers if t in cmap}
    inv = {v: k for k, v in corps.items()}
    print(f"대상 {len(corps)}개 종목 (DART 매칭)")

    this_year = dt.date.today().year
    years = range(FUND_START, this_year + 1) if backfill else range(this_year - 1, this_year + 1)
    codes = list(corps.values())
    batches = [codes[i:i + BATCH] for i in range(0, len(codes), BATCH)]
    jobs = [(key, b, str(yr), rc) for yr in years for rc, _ in RC for b in batches]
    # 증분 모드라도 DB에 아직 없는 종목(유니버스 신규 편입)은 처음부터 백필한다
    if not backfill and (OUT / "financials.csv.gz").exists():
        have = set(pd.read_csv(OUT / "financials.csv.gz")["ticker"].str.lstrip("A"))
        fresh = [corps[t] for t in corps if t not in have]
        if fresh:
            fb = [fresh[i:i + BATCH] for i in range(0, len(fresh), BATCH)]
            jobs += [(key, b, str(yr), rc) for yr in range(FUND_START, this_year - 1)
                     for rc, _ in RC for b in fb]
            print(f"신규 종목 {len(fresh)}개 전체 백필 포함")
    print(f"API 호출 {len(jobs)}건 ({'백필' if backfill else '증분'})...")

    raw = {}
    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(fetch_batch, jobs):
            raw.update(r)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(jobs)}", flush=True)

    # (ticker, yr, qn) -> 누적값
    rows = {}
    for (cc, yr, rc), rec in raw.items():
        qn = dict(RC)[rc]
        t = inv.get(cc)
        if t is None:
            continue
        rows[(t, int(yr), qn)] = {
            "rev": rec.get("매출액", (None,))[0],
            "ebit": rec.get("영업이익", (None,))[0],
            "ni": rec.get("당기순이익", (None,))[0],
            "eq": rec.get("자본총계", (None,))[0],
            "fs": rec.get("매출액", (None, ""))[1] or rec.get("자본총계", (None, ""))[1],
        }
    print(f"수집된 (종목,분기): {len(rows)}")

    # 기존 DB와 병합 (증분 모드에서 과거 데이터 유지)
    db_path = OUT / "financials.csv.gz"
    old = {}
    if db_path.exists() and not backfill:
        prev = pd.read_csv(db_path)
        for _, r in prev.iterrows():
            yr, qn = int(r["q"][:4]), int(r["q"][-1])
            old[(str(r["ticker"]).lstrip("A"), yr, qn)] = None  # 자리 표시
        # 과거 누적값 재구성은 불가하므로, 증분 병합은 '단독값' 단계에서 수행
    # 누적 -> 단독 변환
    QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    out_rows = []
    tick_set = {t for (t, _, _) in rows}
    for t in tick_set:
        sub = {(yr, qn): v for (tt, yr, qn), v in rows.items() if tt == t}
        for (yr, qn) in sorted(sub):
            v = dict(sub[(yr, qn)])
            if qn == 4:
                for k in ("rev", "ebit", "ni"):
                    cum, ok = 0, True
                    for q2 in (1, 2, 3):
                        q = sub.get((yr, q2), {})
                        if q.get(k) is None:
                            ok = False
                            break
                        cum += q[k]
                    v[k] = (v[k] - cum) if (ok and v[k] is not None) else None
            m, d = QEND[qn]
            out_rows.append({"ticker": "A" + t, "q": f"{yr}Q{qn}",
                             "date": dt.date(yr, m, d).isoformat(),
                             "rev": v["rev"], "ebit": v["ebit"], "ni": v["ni"],
                             "eq": v["eq"], "fs": v.get("fs", "")})
    new = pd.DataFrame(out_rows)

    if db_path.exists() and not backfill and len(new):
        prev = pd.read_csv(db_path)
        merged = pd.concat([prev[~prev.set_index(["ticker", "q"]).index
                                 .isin(new.set_index(["ticker", "q"]).index)], new])
    else:
        merged = new
    merged = merged.sort_values(["ticker", "q"]).reset_index(drop=True)
    with gzip.open(db_path, "wt", encoding="utf-8", newline="") as f:
        merged.to_csv(f, index=False)
    (OUT / "meta.json").write_text(json.dumps(
        {"updated": dt.date.today().isoformat(),
         "tickers": int(merged["ticker"].nunique()),
         "rows": int(len(merged))}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK — 종목 {merged['ticker'].nunique()}개, {len(merged)}행 → {db_path}")
    print("이제: git add data/findb && git commit -m 'findb update' && git push")


if __name__ == "__main__":
    main()
