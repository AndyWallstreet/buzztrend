# -*- coding: utf-8 -*-
"""Circle Chart 월간 앨범차트 전체 수집 — 유통사(de_nm)별 출하량 집계용.

Usage:
    python circle_dist_update.py                 # 빠진 달만 (2011-01 ~ 지난달)
    python circle_dist_update.py --from 2011     # 시작 연도 지정
    python circle_dist_update.py --refresh       # 전부 다시

산출 (data/yg/):
    circle_monthly_all.csv  month,rank,album,artist,dist,sales   (톱100, 출하량-반품량)

왜: YG플러스는 음반·음원 유통사라서, Circle 차트의 유통사 칸이 'YG PLUS'인 앨범 출하량이
    곧 이 회사가 유통한 물량임. 이걸 분기로 묶어 음악서비스매출·용역매출과 비교한다.
한계: Circle은 톱100만 공개 → 순위 밖 롱테일은 빠짐(과소집계). 유통사명은 시기에 따라
    'YG PLUS' / 'YG플러스' 등으로 달라져 aggregate 쪽에서 정규화한다.
"""
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

DATA = Path(__file__).resolve().parent / "data" / "yg"
OUT = DATA / "circle_monthly_all.csv"
API = "https://circlechart.kr/data/api/chart/album"
UA = {"User-Agent": "Mozilla/5.0",
      "Referer": "https://circlechart.kr/page_chart/album.circle"}


def fetch_month(year: int, month: int):
    r = requests.post(API, data={"nationGbn": "T", "termGbn": "month", "hitYear": str(year),
                                 "targetTime": f"{month:02d}", "yearTime": "3",
                                 "curUrl": "circlechart.kr/page_chart/album.circle"},
                      headers=UA, timeout=60)
    r.raise_for_status()
    L = r.json().get("List", {}) or {}
    items = list(L.values()) if isinstance(L, dict) else L
    out = []
    for it in items:
        try:
            sales = float(str(it.get("Album_CNT") or 0).replace(",", ""))
        except Exception:
            sales = 0.0
        out.append({"month": f"{year}-{month:02d}",
                    "rank": it.get("SERVICE_RANKING"),
                    "album": (it.get("ALBUM_NAME") or "").strip(),
                    "artist": (it.get("ARTIST_NAME") or "").strip(),
                    "dist": (it.get("de_nm") or "").strip(),
                    "sales": sales})
    return out


def main():
    refresh = "--refresh" in sys.argv
    y0 = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 2011
    DATA.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(OUT) if OUT.exists() and not refresh else pd.DataFrame(columns=["month"])
    have = set(old["month"].astype(str)) if len(old) else set()
    today = dt.date.today()
    # 월간 차트는 다음 달 중순 발표 → 지난달(또는 전전달)까지만
    last = today.replace(day=1) - dt.timedelta(days=1)
    if today.day < 15:
        last = last.replace(day=1) - dt.timedelta(days=1)
    rows, got = [], 0
    for y in range(y0, last.year + 1):
        for m in range(1, 13):
            if (y, m) > (last.year, last.month):
                break
            key = f"{y}-{m:02d}"
            if key in have:
                continue
            try:
                r = fetch_month(y, m)
            except Exception as e:
                print(f"  {key}: 실패 {type(e).__name__}")
                continue
            if not r:
                continue
            rows += r
            got += 1
            if got % 12 == 0:
                print(f"  {key} 까지 {got}개월", flush=True)
            time.sleep(0.5)
    if not rows:
        print("새로 받은 달 없음")
        return
    new = pd.concat([old, pd.DataFrame(rows)], ignore_index=True) if len(old) else pd.DataFrame(rows)
    new = new.drop_duplicates(subset=["month", "album", "artist"], keep="last").sort_values(["month", "rank"])
    new.to_csv(OUT, index=False, encoding="utf-8")
    print(f"circle_monthly_all.csv: {new['month'].min()}~{new['month'].max()}, {len(new):,}행 (이번에 {got}개월 추가)")


if __name__ == "__main__":
    main()
