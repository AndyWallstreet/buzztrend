# -*- coding: utf-8 -*-
"""속보용 절대검색량(구글애즈 엔드포인트)을 '지난달이 나오면' 자동으로 16개국 받기.

왜 (PM 2026-11-04): 9월치는 본 데이터보다 속보용이 1주 먼저 나왔는데(10/15 수동), 손으로 돌려야 했다.
    이제는 매일 도는 findb_weekly.bat 안에서
      1) 매월 12일 이후, 지난달이 아직 absvol_gads.csv 에 없을 때만
      2) 미국 검색어 2개로 싸게 찔러보고 ($0.09)
      3) 지난달이 보이면 그때 absvol_gads_pull.py ALL 을 돌린다 ($1.26, 월 1회)
    찔러보기는 하루 1번이라 늦어도 월 $1 미만.

Usage: python absvol_gads_auto.py [--force]
"""
import base64
import datetime as dt
import json
import sys

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from cosmetics_absvol_update import DATA, _creds
import absvol_gads_pull

META = DATA / "absvol_gads_meta.json"
API = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"


def main():
    force = "--force" in sys.argv
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    have = ""
    if META.exists():
        have = str(json.loads(META.read_text(encoding="utf-8")).get("months", ["", ""])[1])
    if not force:
        if have >= prev:
            print(f"gads 속보: 지난달({prev})까지 이미 있음 — 스킵")
            return 0
        if today.day < 12:
            print(f"gads 속보: {today} 12일 전이라 스킵 (보유 ~{have})")
            return 0
    login, pw = _creds()
    if not login:
        print("DataForSEO 키 없음")
        return 1
    auth = base64.b64encode(f"{login}:{pw}".encode()).decode()
    r = requests.post(API, json=[{"keywords": ["cosrx", "anua"], "location_code": 2840, "language_code": "en"}],
                      headers={"Authorization": "Basic " + auth}, timeout=90)
    r.raise_for_status()
    js = r.json()
    task = (js.get("tasks") or [{}])[0]
    if task.get("status_code") != 20000:
        print("gads 속보 probe 오류:", task.get("status_message"))
        return 1
    months = {f"{m['year']}-{m['month']:02d}" for it in task.get("result") or []
              for m in it.get("monthly_searches") or []}
    latest = max(months) if months else ""
    print(f"gads 속보 probe: 최신 달 {latest} (비용 ${js.get('cost')})")
    if latest < prev and not force:
        print(f"  지난달({prev}) 아직 없음 — 내일 다시")
        return 0
    print("  지난달 나옴 → 16개국 전체 수집")
    sys.argv = ["absvol_gads_pull.py", "ALL"]
    return absvol_gads_pull.main()


if __name__ == "__main__":
    sys.exit(main())
