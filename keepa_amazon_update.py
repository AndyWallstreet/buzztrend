# -*- coding: utf-8 -*-
"""센텔리안24 아마존(미국) 일일 수집 — Keepa API.

왜 Keepa인가: 아마존은 자동 수집을 약관으로 금지한다. Keepa는 아마존 데이터를
정식으로 파는 업체라 API로 받아 쓰는 것은 문제가 없다.

Usage:
    python keepa_amazon_update.py            # 오늘치 수집 (하루 1회 가드)
    python keepa_amazon_update.py --force    # 가드 무시

키:
    환경변수 KEEPA_KEY  (클라우드 루틴은 이걸로)
    또는 .streamlit/secrets.toml 의 [keepa] key = "..."   (로컬, 커밋 금지)

산출물 (data/cosmetics/):
    amazon_daily.csv   date,asin,product,price_usd,price_krw,rating,reviews,
                       monthly_sold,sales_rank,rank_category,offers,stock,source
    amazon_daily_meta.json
"""
import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
OUT = DATA / "amazon_daily.csv"
META = DATA / "amazon_daily_meta.json"
API = "https://api.keepa.com/product"
DOMAIN_US = 1

# 센텔리안24 미국 리스팅 (manual_amazon.csv 에서 확인된 ASIN)
ASINS = {
    "B0DFY92NDB": "Madeca 크림 타임 리버스 50ml",
    "B0FVY91T1Q": "Madeca 크림 타임 리버스 Zero 79.85ml",
    "B0DJ8FQDYL": "Madeca 크림 타임 리버스 2팩 50ml x2",
    "B0GDQWJ658": "Madeca 크림 타임 리버스 세트 2x50ml+마스크",
    "B0FN2T9V8J": "Madeca Mela 캡처 캡슐 크림 54.71ml",
    "B0DSNLM3T1": "360 Shot PDRN 액티브 세럼 50ml",
    "B0BS2T3QYF": "Madeca 크림 시즌6 50.3ml",
    "B0BTX77JYZ": "Madeca 주름 캡처 스틱",
}

# Keepa csv 배열 인덱스 (keepa.com/api-docs/product-object.html)
# 주의: 7·18·19~29·32번은 한 기록이 (시각, 가격, 배송비) 3칸이다 — stride 3.
I_AMAZON, I_NEW, I_SALES, I_LISTPRICE = 0, 1, 3, 4
I_RATING, I_REVIEWS, I_BUYBOX = 16, 17, 18
I_COUNT_NEW = 11
STRIDE3 = {7, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 32}
AVAIL = {-1: "아마존 미판매", 0: "재고 있음", 1: "예약주문", 2: "알 수 없음",
         3: "이월주문", 4: "출고 지연"}
FIELDS = ["date", "asin", "product", "price_usd", "price_krw", "list_usd",
          "rating", "reviews", "monthly_sold", "sales_rank", "rank_drops_30d",
          "offers", "stock", "source"]


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


def _last(csv_arr, idx):
    """csv[idx]의 마지막 값. 3칸짜리 행(가격+배송비)은 가격만 집는다.
    없거나 -1(데이터 없음/품절)이면 None."""
    if not csv_arr or idx >= len(csv_arr) or not csv_arr[idx]:
        return None
    a = csv_arr[idx]
    stride = 3 if idx in STRIDE3 else 2
    if len(a) < stride:
        return None
    v = a[-stride + 1]
    return None if v is None or v < 0 else v


def _usdkrw():
    """환율 — 실패해도 수집은 계속한다(원화 열만 빈칸)."""
    try:
        r = requests.get("https://api.frankfurter.app/latest",
                         params={"from": "USD", "to": "KRW"}, timeout=20)
        return r.json()["rates"]["KRW"]
    except Exception:
        return None


def main():
    force = "--force" in sys.argv
    key = _key()
    if not key:
        print("KEEPA_KEY 없음 — 환경변수 또는 .streamlit/secrets.toml [keepa] key 설정 필요")
        return 1
    today = dt.date.today().isoformat()
    rows_old = []
    if OUT.exists():
        rows_old = list(csv.DictReader(OUT.open(encoding="utf-8")))
        if not force and any(r["date"] == today for r in rows_old):
            print(f"{today} 수집본 이미 있음 - 스킵 (--force 로 무시)")
            return 0

    # 토큰: 기본 1/ASIN + rating 1 + buybox 2 = ASIN당 약 4토큰 (8개면 32).
    # offers/stock은 6토큰/페이지라 쓰지 않는다 — 재고는 availabilityAmazon으로 충분.
    # stats=30은 무료. update=24 는 24시간 이내 데이터면 그대로 써서 추가 토큰 회피.
    r = requests.get(API, params={"key": key, "domain": DOMAIN_US,
                                  "asin": ",".join(ASINS), "stats": 30,
                                  "rating": 1, "buybox": 1, "update": 24},
                     timeout=120)
    if r.status_code == 429:
        print("Keepa 토큰 소진 — refillIn(ms):",
              (r.json() or {}).get("refillIn"))
        return 1
    r.raise_for_status()
    js = r.json()
    if js.get("error"):
        print("Keepa 오류:", js["error"])
        return 1
    fx = _usdkrw()
    new = []
    for p in js.get("products") or []:
        asin = p.get("asin")
        c = p.get("csv") or []
        st = p.get("stats") or {}
        cur = st.get("current") or []

        def pick(idx):
            v = cur[idx] if idx < len(cur) else None
            if v is None or v < 0:
                v = _last(c, idx)
            return v

        price = pick(I_BUYBOX) or pick(I_AMAZON) or pick(I_NEW)
        listp = pick(I_LISTPRICE)
        rating = pick(I_RATING)
        reviews = pick(I_REVIEWS)
        rank = pick(I_SALES)
        offers = st.get("totalOfferCount")
        if offers in (None, -1, -2):
            offers = pick(I_COUNT_NEW)
        avail = p.get("availabilityAmazon")
        new.append({
            "date": today, "asin": asin,
            "product": ASINS.get(asin, p.get("title", "")[:60]),
            "price_usd": round(price / 100, 2) if price else "",
            "price_krw": round(price / 100 * fx) if (price and fx) else "",
            "list_usd": round(listp / 100, 2) if listp else "",
            "rating": round(rating / 10, 1) if rating else "",
            "reviews": reviews or "",
            "monthly_sold": p.get("monthlySold") or "",
            "sales_rank": rank or "",
            "rank_drops_30d": st.get("salesRankDrops30", ""),
            "offers": offers if offers not in (None, -1, -2) else "",
            "stock": AVAIL.get(avail, "") if avail is not None else "",
            "source": "Keepa API (amazon.com)",
        })
    if not new:
        print("결과 비어 있음 — 응답 확인 필요:", str(js)[:300])
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    keep = [r for r in rows_old if r["date"] != today]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in keep + new:
            w.writerow({k: row.get(k, "") for k in FIELDS})
    META.write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "date": today, "asins": len(new),
         "tokens_left": js.get("tokensLeft"),
         "tokens_consumed": js.get("tokensConsumed"),
         "refill_rate_per_min": js.get("refillRate"),
         "source": "Keepa API /product domain=1 (stats=30, rating=1, buybox=1)"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"amazon_daily.csv: {today} {len(new)}개 ASIN | 토큰 잔여 "
          f"{js.get('tokensLeft')}")
    for row in new:
        print(f"  {row['asin']} {row['product'][:26]:26s} "
              f"${row['price_usd']} ★{row['rating']} 리뷰{row['reviews']} "
              f"월구매{row['monthly_sold']} BSR{row['sales_rank']} "
              f"{row['stock']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
