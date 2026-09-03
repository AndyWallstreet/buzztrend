# -*- coding: utf-8 -*-
"""YG 아티스트 앨범 판매 — Circle Chart 월간/주간 자동 수집.

Usage:
    python yg_circle_update.py            # 빠진 기간만 증분 수집
    python yg_circle_update.py --refresh  # 2026년 전체 다시 수집

산출물 (data/yg/):
    yg_albums_monthly.csv  월간 차트의 YG 앨범 행 (2026-01부터)
    yg_albums_weekly.csv   주간 차트의 YG 앨범 행 (2026년 27주=7월부터)

주의:
- Circle 차트는 톱100만 공개 → 순위 밖으로 밀린 구작의 롱테일 판매는 빠짐 (과소집계).
- 유통사 'YG PLUS'는 HYBE 물량까지 유통하므로 유통사 필터는 쓰지 않고
  YG 소속 아티스트 이름 화이트리스트로 거른다.
- 집계 기준: 출하량-반품량 (Circle 공식 기준).
"""
import datetime as dt
import re
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
API = "https://circlechart.kr/data/api/chart/album"
UA = {"User-Agent": "Mozilla/5.0",
      "Referer": "https://circlechart.kr/page_chart/album.circle"}

# YG 소속 (워크북 Album 시트 로스터와 동일 그룹핑)
YG_MAP = {
    "BLACKPINK": ["BLACKPINK", "블랙핑크"],
    "BABYMONSTER": ["BABYMONSTER", "베이비몬스터"],
    "TREASURE": ["TREASURE", "트레저"],
    "BIGBANG": ["BIGBANG", "빅뱅"],
    "WINNER": ["WINNER", "위너"],
    "AKMU": ["AKMU", "악뮤", "악동뮤지션"],
    "2NE1": ["2NE1", "투애니원"],
    "iKON": ["IKON", "아이콘"],
}
WEEK1_SUN = dt.date(2025, 12, 28)   # 2026년 1주차 시작(일요일) — W35=08.23~29로 검산
YEAR = 2026
WEEK_FROM = 27                       # 7월 시작 주


def yg_group(artist: str):
    up = artist.upper()
    for grp, keys in YG_MAP.items():
        if any(k.upper() in up for k in keys):
            return grp
    return None


def fetch_chart(term: str, target: str):
    """term: 'month'|'week', target: '06'|'35' -> YG 행 리스트."""
    r = requests.post(API, data={"nationGbn": "T", "termGbn": term,
                                 "hitYear": str(YEAR), "targetTime": target,
                                 "yearTime": "3",
                                 "curUrl": "circlechart.kr/page_chart/album.circle"},
                      timeout=25, headers=UA)
    j = r.json()
    lst = j.get("List") or {}
    items = list(lst.values()) if isinstance(lst, dict) else lst
    out = []
    for rank, it in enumerate(items, 1):
        grp = yg_group(it.get("ARTIST_NAME", ""))
        if grp is None:
            continue
        try:
            cnt = int(str(it.get("Album_CNT", "0")).replace(",", ""))
        except ValueError:
            continue
        out.append({"group": grp, "artist": it.get("ARTIST_NAME", "").strip(),
                    "album": it.get("ALBUM_NAME", "").strip(),
                    "sales": cnt, "rank": rank,
                    "dist": it.get("de_nm", "")})
    return out, len(items)


def week_range(w: int):
    s = WEEK1_SUN + dt.timedelta(days=(w - 1) * 7)
    return s, s + dt.timedelta(days=6)


def main():
    refresh = "--refresh" in sys.argv
    DATA.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()

    # ---- 월간 (1월 ~ 완료된 직전 월)
    mp = DATA / "yg_albums_monthly.csv"
    prev_m = pd.read_csv(mp, dtype=str) if mp.exists() and not refresh else \
        pd.DataFrame(columns=["period"])
    have_m = set(prev_m["period"]) if len(prev_m) else set()
    last_full_month = today.month - 1 if today.day >= 15 else today.month - 2
    rows_m = []
    for m in range(1, max(last_full_month, 0) + 1):
        period = f"{YEAR}-{m:02d}"
        if period in have_m:
            continue
        got, total = fetch_chart("month", f"{m:02d}")
        if total == 0:      # 아직 미발표
            continue
        for g in got:
            g["period"] = period
        rows_m += got
        print(f"월간 {period}: 차트 {total}행 중 YG {len(got)}행")
        time.sleep(0.6)
    if rows_m:
        new_m = pd.concat([prev_m, pd.DataFrame(rows_m)], ignore_index=True)
        new_m.to_csv(mp, index=False, encoding="utf-8")

    # ---- 주간 (27주 = 7월 ~ 지난 주)
    wp = DATA / "yg_albums_weekly.csv"
    prev_w = pd.read_csv(wp, dtype=str) if wp.exists() and not refresh else \
        pd.DataFrame(columns=["week"])
    have_w = set(prev_w["week"].astype(str)) if len(prev_w) else set()
    cur_week = (today - WEEK1_SUN).days // 7 + 1
    rows_w = []
    for w in range(WEEK_FROM, cur_week):     # 진행 중인 주는 제외
        if str(w) in have_w:
            continue
        got, total = fetch_chart("week", f"{w:02d}")
        if total == 0:
            continue
        ws, we = week_range(w)
        for g in got:
            g.update({"week": w, "start": ws.isoformat(), "end": we.isoformat()})
        rows_w += got
        print(f"주간 W{w} ({ws}~{we}): YG {len(got)}행")
        time.sleep(0.6)
    if rows_w:
        new_w = pd.concat([prev_w, pd.DataFrame(rows_w)], ignore_index=True)
        new_w.to_csv(wp, index=False, encoding="utf-8")

    print("완료 — 이제: git add data/yg && git commit && git push")


if __name__ == "__main__":
    main()
