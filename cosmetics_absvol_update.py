# -*- coding: utf-8 -*-
"""K뷰티 브랜드 절대 검색량 — DataForSEO (구글 애즈 월 검색수), 주 1회.

Usage:
    python cosmetics_absvol_update.py [--force]

키 (둘 중 하나에 두면 됨 — 저장소에 커밋 금지):
    .streamlit/secrets.toml:
        [dataforseo]
        login = "가입 이메일"
        password = "API 비밀번호(대시보드에서 확인)"
    또는 환경변수 DFS_LOGIN / DFS_PASSWORD

산출물 (data/cosmetics/):
    absvol_monthly.csv   month,brand,keyword,searches — 브랜드별 월 검색수(절대량)
    absvol_meta.json
    ../..//kbeauty/data/raw 아님 — 원시 응답은 absvol_raw.json (디버그용, gitignore 대상 아님/작음)

- 엔드포인트: POST /v3/keywords_data/google_ads/search_volume/live
  (구글 애즈 기준 월 검색수 + monthly_searches 이력, 미국 location_code 2840)
- 비용: 요청 1건 약 $0.1 안팎 (키워드 1,000개까지 동일) — 주 1회면 월 $0.5 수준
- 주 1회 가드: 최근 6일 내 수집본 있으면 스킵 (--force 로 무시)
- 브랜드 목록은 cosmetics_lifecycle_update.BRANDS 재사용 (미국 키워드)
"""
import base64
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from cosmetics_lifecycle_update import BRANDS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
OUT = DATA / "absvol_monthly.csv"
API = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
LOCATION_US = 2840


def _creds():
    login = os.environ.get("DFS_LOGIN")
    pw = os.environ.get("DFS_PASSWORD")
    if login and pw:
        return login, pw
    sec = ROOT / ".streamlit" / "secrets.toml"
    if sec.exists():
        import tomllib
        cfg = tomllib.loads(sec.read_text(encoding="utf-8"))
        d = cfg.get("dataforseo", {})
        if d.get("login") and d.get("password"):
            return d["login"], d["password"]
    return None, None


def main():
    force = "--force" in sys.argv
    login, pw = _creds()
    if not login:
        print("DataForSEO 키 없음: .streamlit/secrets.toml [dataforseo] 또는 "
              "DFS_LOGIN/DFS_PASSWORD 설정 후 다시 실행. (이번 회차 스킵)")
        return
    meta_p = DATA / "absvol_meta.json"
    if OUT.exists() and meta_p.exists() and not force:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        last = dt.datetime.fromisoformat(meta["fetched"])
        if (dt.datetime.now() - last).days < 6:
            print(f"최근 수집본 있음 ({meta['fetched'][:10]}) - 주 1회 가드로 스킵")
            return

    kw2brand = {v.get("US", v["*"]): b for b, v in BRANDS.items()}
    auth = base64.b64encode(f"{login}:{pw}".encode()).decode()
    body = [{"keywords": list(kw2brand), "location_code": LOCATION_US,
             "language_code": "en"}]
    r = requests.post(API, json=body,
                      headers={"Authorization": "Basic " + auth}, timeout=90)
    r.raise_for_status()
    js = r.json()
    (DATA / "absvol_raw.json").write_text(
        json.dumps(js, ensure_ascii=False)[:400000], encoding="utf-8")
    task = (js.get("tasks") or [{}])[0]
    if task.get("status_code") != 20000:
        print("API 오류:", task.get("status_code"), task.get("status_message"))
        return

    rows = []
    for it in task.get("result") or []:
        kw = it.get("keyword", "")
        brand = kw2brand.get(kw, kw)
        for m in it.get("monthly_searches") or []:
            rows.append({"month": f"{m['year']}-{m['month']:02d}",
                         "brand": brand, "keyword": kw,
                         "searches": m.get("search_volume") or 0})
    if not rows:
        print("결과 비어 있음 - absvol_raw.json 확인 필요")
        return
    new = pd.DataFrame(rows)
    if OUT.exists():                       # 이력 보존: 과거 월은 유지, 겹치면 최신값
        old = pd.read_csv(OUT)
        new = (pd.concat([old, new])
               .drop_duplicates(subset=["month", "brand"], keep="last"))
    new = new.sort_values(["brand", "month"])
    new.to_csv(OUT, index=False, encoding="utf-8")
    cost = js.get("cost")
    meta_p.write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "location": "US(2840)", "source": "DataForSEO google_ads "
         "search_volume", "cost_usd": cost,
         "months": [new["month"].min(), new["month"].max()]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"absvol_monthly.csv: {new['brand'].nunique()}개 브랜드, "
          f"{new['month'].min()}~{new['month'].max()} | 이번 요청 비용 ${cost}")


if __name__ == "__main__":
    main()
