# -*- coding: utf-8 -*-
"""K뷰티 브랜드별 아마존 BSR 과거 이력 — Keepa API.

왜: 퍼널(상대검색 → 절대검색 → BSR → 매출)에서 매출 점이 너무 적다.
    비상장 브랜드는 연 1회 공시라 브랜드당 3~6점뿐이고, 18개 중 12개는
    상관 계산 자체가 안 된다. BSR 은 일간이라 브랜드당 수백 점이 생긴다.
    BSR 이 매출 대리 지표로 쓸 만한지 먼저 확인하고, 되면 공시가 드문
    브랜드(센텔리안24 포함)를 주간으로 추적한다.

Usage:
    python keepa_bsr_history.py --discover        # 브랜드 → ASIN 찾기 (브랜드당 10토큰)
    python keepa_bsr_history.py                   # BSR 이력 받기 (ASIN당 1토큰)
    python keepa_bsr_history.py --brand cosrx     # 한 브랜드만
    python keepa_bsr_history.py --domain 5        # 일본 아마존 (기본 1 = 미국)

키: 환경변수 KEEPA_KEY 또는 .streamlit/secrets.toml 의 [keepa] key
    (secrets.toml 은 gitignore — 절대 커밋하지 말 것)

산출 (data/cosmetics/):
    bsr_asins{suffix}.csv     brand,asin,title   ← --discover 결과, 손으로 고쳐도 됨
    bsr_daily{suffix}.csv     brand,asin,date,bsr
    bsr_monthly{suffix}.csv   brand,month,bsr_median,bsr_strength,n_asin
    bsr_meta{suffix}.json

주의: BSR 은 숫자가 작을수록 잘 팔린다. 그대로 쓰면 상관 부호가 뒤집혀 읽기 어렵다.
      그래서 bsr_strength = -log10(BSR) 을 같이 저장한다 (클수록 잘 팔림).

토큰(Starter 20/분 = 월 892,800 기준): 최초 수집 약 234, 주간 추적 월 약 216.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
META_URL = "https://api.keepa.com"
I_SALES = 3                       # csv[3] = SALES rank
# Keepa 시간 = (unix_ms / 60000) - 21564000  →  unix_ms = (분 + 21564000) * 60000.
# 21564000 은 '분' 단위다. ms 로 더하려면 x60000 해야 한다 — 이걸 빠뜨려서
# 날짜가 1974년으로 나왔다(2026-10-15).
KEEPA_EPOCH_MS = 21564000 * 60000      # = 1,293,840,000,000 (2011-01-01 UTC)
DOMAINS = {1: "us", 5: "jp", 3: "uk", 4: "de"}

# funnel_study.MAP 과 같은 브랜드. 값 = 아마존에 등록된 브랜드명.
BRANDS = {
    "madeca cream": "Centellian 24", "reedle shot": "VT", "atopalm": "Atopalm",
    "medicube": "medicube", "d'alba": "d'Alba", "manyo": "Manyo",
    "laneige": "LANEIGE", "anua": "Anua", "cosrx": "COSRX",
    "skin1004": "SKIN1004", "beauty of joseon": "Beauty of Joseon",
    "tirtir": "TIRTIR", "torriden": "TORRIDEN", "numbuzin": "numbuzin",
    "round lab": "Round Lab", "abib": "Abib", "mixsoon": "mixsoon",
    "biodance": "BIODANCE",
}
TOP_N = 3            # 브랜드당 대표 ASIN 수 (많이 팔리는 순)


def paths(domain):
    sfx = "" if domain == 1 else "_" + DOMAINS.get(domain, str(domain))
    return (DATA / f"bsr_asins{sfx}.csv", DATA / f"bsr_daily{sfx}.csv",
            DATA / f"bsr_monthly{sfx}.csv", DATA / f"bsr_meta{sfx}.json")


def _key():
    k = os.environ.get("KEEPA_KEY")
    if k:
        return k.strip()
    sec = ROOT / ".streamlit" / "secrets.toml"
    if sec.exists():
        import tomllib
        return (tomllib.loads(sec.read_text(encoding="utf-8"))
                .get("keepa", {}).get("key"))
    return None


def _call(path, key, body=None, **params):
    """429(토큰 소진)면 Keepa 가 알려주는 만큼 기다렸다 재시도. 밤새 돌려도 되게.
    body 가 있으면 POST (Product Finder 는 POST 전용).

    주의: 예외 메시지에 요청 URL 을 그대로 넣으면 키가 로그에 남는다.
    실제로 한 번 유출됐다(2026-10-15) — 반드시 키를 지우고 올린다."""
    for attempt in range(60):
        params["key"] = key
        if body is None:
            r = requests.get(f"{META_URL}/{path}", params=params, timeout=120)
        else:
            r = requests.post(f"{META_URL}/{path}", params=params, json=body,
                              timeout=120)
        if r.status_code == 429:
            wait = ((r.json() or {}).get("refillIn") or 60000) / 1000 + 2
            print(f"    토큰 소진 — {wait:.0f}초 대기 ({attempt + 1}회차)")
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} "
                               + r.text[:200].replace(key, "<KEY>"))
        js = r.json()
        if js.get("error"):
            raise RuntimeError(str(js["error"]).replace(key, "<KEY>"))
        return js
    raise RuntimeError("토큰 대기 60회 초과")


def discover(key, domain):
    """Product Finder 로 브랜드별 대표 ASIN 찾기. 브랜드당 10토큰."""
    asins_csv = paths(domain)[0]
    rows = []
    for b, brand_name in BRANDS.items():
        print(f"  {b:18s} <- 브랜드 '{brand_name}'")
        # perPage 는 50 미만이면 400 ("too small") — 50 받아서 앞에서 TOP_N 만 쓴다.
        # current_SALES_gte=1 은 순위 없는(=안 팔리는) 상품을 뺀다.
        sel = {"brand": [brand_name.lower()], "current_SALES_gte": 1,
               "sort": [["current_SALES", "asc"]], "perPage": 50, "page": 0}
        try:
            js = _call("query", key, body=sel, domain=domain)
        except Exception as e:
            print(f"    실패: {e}")
            continue
        found = (js.get("asinList") or [])[:TOP_N]
        if not found:
            print("    결과 없음 — bsr_asins.csv 에 손으로 넣어야 함")
            continue
        for a in found:
            rows.append({"brand": b, "asin": a, "title": ""})
        print(f"    {len(found)}개: {', '.join(found)}")
    DATA.mkdir(parents=True, exist_ok=True)
    with asins_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "title"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n{asins_csv.name}: {len(rows)}개 ASIN "
          f"({len({r['brand'] for r in rows})}개 브랜드)")
    return rows


def history(key, domain, only_brand=None):
    asins_csv, daily, monthly, meta_p = paths(domain)
    if not asins_csv.exists():
        print(f"{asins_csv.name} 없음 — 먼저 --discover 로 ASIN 을 찾을 것")
        return 1
    rows = list(csv.DictReader(asins_csv.open(encoding="utf-8-sig")))
    todo = [r for r in rows if not only_brand or r["brand"] == only_brand]
    out, meta = [], {}
    for i, r in enumerate(todo, 1):
        asin, b = r["asin"].strip(), r["brand"]
        if not asin:
            continue
        print(f"  [{i}/{len(todo)}] {b:18s} {asin}")
        js = _call("product", key, domain=domain, asin=asin, history=1,
                   stats=0)
        prods = js.get("products") or []
        if not prods:
            print("    상품 없음")
            continue
        p = prods[0]
        arr = p.get("csv") or []
        series = arr[I_SALES] if len(arr) > I_SALES else None
        if not series:
            print("    BSR 이력 없음 (아마존 판매 기록 없음)")
            continue
        # csv[3] 은 [시각(분), 값, 시각, 값, ...]. -1 은 '값 없음'.
        n = 0
        for j in range(0, len(series) - 1, 2):
            t, v = series[j], series[j + 1]
            if v is None or v < 0:
                continue
            d = dt.datetime.utcfromtimestamp(
                (t * 60000 + KEEPA_EPOCH_MS) / 1000).date()
            out.append({"brand": b, "asin": asin, "date": d.isoformat(),
                        "bsr": v})
            n += 1
        title = (p.get("title") or "")[:70]
        meta[asin] = {"brand": b, "points": n, "title": title}
        print(f"    {n:,}개 점 · {title[:46]}")
        r["title"] = r.get("title") or title
    if not out:
        print("수집된 BSR 없음")
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    with daily.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "date", "bsr"])
        w.writeheader()
        w.writerows(out)

    # 월별: ASIN 별 중앙값 → 브랜드 중앙값 (BSR 은 튀는 값이 많아 평균 쓰면 안 된다)
    byam = {}
    for r in out:
        byam.setdefault((r["brand"], r["date"][:7], r["asin"]), []).append(r["bsr"])
    bybm = {}
    for (b, m, a), vs in byam.items():
        bybm.setdefault((b, m), []).append(statistics.median(vs))
    mrows = []
    for (b, m), vs in sorted(bybm.items()):
        med = statistics.median(vs)
        mrows.append({"brand": b, "month": m, "bsr_median": round(med),
                      "bsr_strength": round(-math.log10(med), 4),
                      "n_asin": len(vs)})
    with monthly.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "month", "bsr_median",
                                          "bsr_strength", "n_asin"])
        w.writeheader()
        w.writerows(mrows)
    with asins_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "title"])
        w.writeheader()
        w.writerows(rows)
    meta_p.write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "domain": DOMAINS.get(domain, domain), "asins": meta,
         "months": len(mrows), "brands": sorted({r["brand"] for r in mrows}),
         "source": f"Keepa API /product domain={domain} history=1, csv[3]=SALES rank",
         "note": "bsr_strength = -log10(BSR). 클수록 잘 팔림."},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{daily.name} {len(out):,}행 · {monthly.name} {len(mrows)}행 "
          f"· {len({r['brand'] for r in mrows})}개 브랜드")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--brand")
    ap.add_argument("--domain", type=int, default=1,
                    help="1=미국(기본) 5=일본 3=영국 4=독일")
    a = ap.parse_args()
    key = _key()
    if not key:
        print("KEEPA_KEY 없음 — 환경변수 또는 .streamlit/secrets.toml [keepa] key")
        print("결제 후 키만 넣으면 이 스크립트는 그대로 돌아감.")
        return 1
    if a.discover:
        discover(key, a.domain)
        return 0
    return history(key, a.domain, a.brand)


if __name__ == "__main__":
    sys.exit(main())
