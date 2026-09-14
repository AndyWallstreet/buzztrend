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

- 엔드포인트: POST /v3/dataforseo_labs/google/historical_search_volume/live
  (구글 애즈 기준 월 검색수, 2018년까지 이력 약 8년치, 미국 location_code 2840)
  ※ keywords_data/google_ads/search_volume은 12개월치만 줘서 안 씀
- 비용: 요청 1건 약 $0.01~0.02 — 주 1회면 월 $0.1 미만
- 주 1회 가드: 최근 6일 내 수집본 있으면 스킵 (--force 로 무시)
- 브랜드 목록은 cosmetics_lifecycle_update.BRANDS 재사용 (미국 키워드)
"""
import base64
import datetime as dt
import json
import os
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

from cosmetics_lifecycle_update import BRANDS

# 절대량 전용 키워드: 브랜드당 여러 검색어를 합산한다(구글애즈는 로마자↔가타카나를
# 묶지 않아 별개 검색어로 잡힘). 2026-09-14 확인: 일본에서 cosrx·skin1004·beauty of
# joseon은 로마자 검색이 가타카나보다 크고, 센텔리안24는 브랜드명+제품명이 갈린다.
# "*" = 기본(모든 나라), "JP" = 일본. 없으면 BRANDS 매핑을 쓴다.
ABS_KEYWORDS = {
    "madeca cream": {"*": ["madeca cream", "centellian 24"],
                     "JP": ["センテリアン24", "マデカクリーム", "madeca cream"]},
    "reedle shot": {"JP": ["リードル ショット", "reedle shot"]},
    "medicube": {"JP": ["メディキューブ", "medicube"]},
    "anua": {"JP": ["アヌア", "anua"]},
    "cosrx": {"JP": ["コスアールエックス", "cosrx"]},
    "tirtir": {"JP": ["ティルティル", "tirtir"]},
    "beauty of joseon": {"JP": ["beauty of joseon"]},
    "torriden": {"JP": ["トリデン", "torriden"]},
    "skin1004": {"JP": ["スキン1004", "skin1004"]},
    "round lab": {"JP": ["ラウンドラボ", "round lab"]},
    "biodance": {"JP": ["バイオダンス", "biodance"]},
    "d'alba": {"JP": ["ダルバ", "d'alba"]},
    "manyo": {"JP": ["魔女工場", "manyo"]},
    "mixsoon": {"JP": ["ミクスーン", "mixsoon"]},
    "numbuzin": {"JP": ["ナンバーズイン", "numbuzin"]},
    "abib": {"JP": ["アビブ", "abib"]},
    "isntree": {"JP": ["イズントゥリー", "isntree"]},
    "laneige": {"JP": ["ラネージュ", "laneige"]},
}


def keywords_for(brand, geo):
    """브랜드·나라별 검색어 목록 (합산 대상)."""
    a = ABS_KEYWORDS.get(brand, {})
    if geo in a:
        return list(a[geo])
    if "*" in a:
        return list(a["*"])
    v = BRANDS[brand]
    return [v.get(geo, v["*"])]

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
OUT = DATA / "absvol_monthly.csv"
API = ("https://api.dataforseo.com/v3/dataforseo_labs/google/"
       "historical_search_volume/live")
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

    auth = base64.b64encode(f"{login}:{pw}".encode()).decode()
    # 나라별 수집: 일본은 가타카나 키워드 (BRANDS의 "JP" 매핑, 없으면 로마자).
    # 주의: 구글 애즈 검색수는 '구글에서의' 검색만 — 야후재팬 프론트(점유 ~6~9%)
    # 는 미포함이라 일본 절대량은 일관되게 약간 과소. 브랜드 간 비교엔 문제 없음.
    GEOS = {"US": (2840, "en"), "JP": (2392, "ja"),
            "GB": (2826, "en"), "AU": (2036, "en"),
            # 2026-09 확장: 로마자 철자 그대로 쓰는 주요 K뷰티 시장 12개국
            "CA": (2124, "en"), "DE": (2276, "de"), "FR": (2250, "fr"),
            "NL": (2528, "nl"), "MX": (2484, "es"), "BR": (2076, "pt"),
            "SG": (2702, "en"), "PH": (2608, "en"), "MY": (2458, "en"),
            "ID": (2360, "id"), "VN": (2704, "vi"), "IN": (2356, "en")}
    rows, total_cost = [], 0.0
    for geo, (loc, lang) in GEOS.items():
        kw2brand = {kw: b for b in BRANDS for kw in keywords_for(b, geo)}
        body = [{"keywords": list(kw2brand), "location_code": loc,
                 "language_code": lang}]
        js = None
        for attempt in range(3):           # 간헐적 403 스로틀 → 재시도
            try:
                r = requests.post(API, json=body,
                                  headers={"Authorization": "Basic " + auth},
                                  timeout=90)
                r.raise_for_status()
                js = r.json()
                break
            except Exception as e:
                print(f"  {geo}: {type(e).__name__} 재시도 {attempt + 1}/3")
                time.sleep(20)
        if js is None:
            print(f"  {geo}: 수집 실패 - 기존 데이터 유지")
            continue
        (DATA / f"absvol_raw_{geo}.json").write_text(
            json.dumps(js, ensure_ascii=False)[:400000], encoding="utf-8")
        task = (js.get("tasks") or [{}])[0]
        if task.get("status_code") != 20000:
            print(f"  {geo} API 오류:", task.get("status_code"),
                  task.get("status_message"))
            continue
        res = (task.get("result") or [{}])[0]
        n0 = len(rows)
        for it in res.get("items") or []:
            kw = it.get("keyword", "")
            brand = kw2brand.get(kw, kw)
            hist = ((it.get("keyword_info") or {}).get("monthly_searches")) or []
            for m in hist:
                rows.append({"geo": geo,
                             "month": f"{m['year']}-{m['month']:02d}",
                             "brand": brand, "keyword": kw,
                             "searches": m.get("search_volume") or 0})
        total_cost += js.get("cost") or 0
        print(f"  {geo}: {len(rows) - n0}행 | 비용 ${js.get('cost')}")
        time.sleep(5)

    # ---- 전세계(WW): google_ads search_volume, location 생략 = worldwide.
    # labs historical은 국가별만 지원 → worldwide는 이 엔드포인트로만. 단 12개월
    # 이력만 주고, 로마자 키워드 1개라 일본어표기 브랜드(리들샷 등)는 과소집계.
    WW_API = ("https://api.dataforseo.com/v3/keywords_data/google_ads/"
              "search_volume/live")
    ww_k2b = {kw: b for b in BRANDS for kw in keywords_for(b, "WW")}
    js = None
    for attempt in range(3):
        try:
            r = requests.post(WW_API, json=[{"keywords": list(ww_k2b)}],
                              headers={"Authorization": "Basic " + auth},
                              timeout=90)
            r.raise_for_status()
            js = r.json()
            break
        except Exception as e:
            print(f"  WW: {type(e).__name__} 재시도 {attempt + 1}/3")
            time.sleep(20)
    if js is not None:
        task = (js.get("tasks") or [{}])[0]
        if task.get("status_code") == 20000:
            n0 = len(rows)
            for it in task.get("result") or []:
                kw = it.get("keyword", "")
                brand = ww_k2b.get(kw, kw)
                for m in it.get("monthly_searches") or []:
                    rows.append({"geo": "WW",
                                 "month": f"{m['year']}-{m['month']:02d}",
                                 "brand": brand, "keyword": kw,
                                 "searches": m.get("search_volume") or 0})
            total_cost += js.get("cost") or 0
            print(f"  WW(전세계): {len(rows) - n0}행 | 비용 ${js.get('cost')}")
        else:
            print("  WW API 오류:", task.get("status_message"))
    else:
        print("  WW: 수집 실패 - 기존 데이터 유지")

    if not rows:
        print("결과 비어 있음 - absvol_raw_*.json 확인 필요")
        return
    new = pd.DataFrame(rows)
    if OUT.exists():                       # 이력 보존: 과거 월은 유지, 겹치면 최신값
        old = pd.read_csv(OUT)
        if "geo" not in old.columns:       # 구버전 파일은 미국 수집분
            old["geo"] = "US"
        # 이번에 새로 받은 (나라, 브랜드)는 통째로 교체 — 검색어 목록이 바뀌어도
        # 옛 검색어 행이 남아 이중 합산되는 일을 막는다. 실패한 나라는 기존값 유지.
        got = set(zip(new["geo"], new["brand"]))
        old = old[[(g, b) not in got for g, b in zip(old["geo"], old["brand"])]]
        new = (pd.concat([old, new])
               .drop_duplicates(subset=["geo", "month", "brand", "keyword"],
                                keep="last"))
    new = new.sort_values(["geo", "brand", "keyword", "month"])
    new.to_csv(OUT, index=False, encoding="utf-8")
    meta_p.write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "geos": {g: f"loc {v[0]}/{v[1]}" for g, v in GEOS.items()},
         "source": "DataForSEO labs historical_search_volume",
         "cost_usd": total_cost,
         "months": [new["month"].min(), new["month"].max()]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"absvol_monthly.csv: {new['brand'].nunique()}개 브랜드 × "
          f"{new['geo'].nunique()}개국, {new['month'].min()}~"
          f"{new['month'].max()} | 총비용 ${total_cost}")


if __name__ == "__main__":
    main()
