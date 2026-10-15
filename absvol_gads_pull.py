# -*- coding: utf-8 -*-
"""절대검색량 '최신 달' 을 구글애즈 엔드포인트로 나라별로 받기.

Usage:
    python absvol_gads_pull.py US JP          # 나라 코드 (기본 US JP)
    python absvol_gads_pull.py ALL            # absvol_meta.json 에 있는 16개국 전부

왜 (PM 2026-10-15): 나라별 본 데이터(dataforseo_labs historical, 8년치)는 지난달 분이
    중순~말에 늦게 올라온다. 구글애즈 엔드포인트(keywords_data/google_ads/search_volume)는
    같은 구글애즈 숫자를 더 빨리 주지만 12개월치뿐이다. 그래서 '최신 달' 만 이걸로 받아
    absvol_gads.csv 에 따로 둔다. 본 파일(absvol_monthly.csv)에는 섞지 않는다 —
    본 데이터가 따라잡으면 그쪽이 정식이고, 이 파일은 속보용이다.

검산: 두 출처가 같은 달(예: 8월)에 같은 값을 주는지 비교해 출력한다. 다르면 섞어 쓰면 안 된다.

산출: data/cosmetics/absvol_gads.csv (geo, brand, keyword, month, searches)
      data/cosmetics/absvol_gads_meta.json
"""
import base64
import datetime as dt
import json
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

from cosmetics_absvol_update import BRANDS, DATA, _creds, keywords_for

API = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
OUT = DATA / "absvol_gads.csv"
META = DATA / "absvol_gads_meta.json"


def geo_codes():
    """absvol_meta.json 의 'US': 'loc 2840/en' 같은 표기에서 location_code·language_code 를 뽑는다."""
    m = json.loads((DATA / "absvol_meta.json").read_text(encoding="utf-8"))
    out = {}
    for g, s in (m.get("geos") or {}).items():
        loc, lang = s.replace("loc ", "").split("/")
        out[g] = (int(loc), lang)
    return out


def main():
    args = [a.upper() for a in sys.argv[1:]] or ["US", "JP"]
    codes = geo_codes()
    geos = list(codes) if args == ["ALL"] else args
    login, pw = _creds()
    if not login:
        print("DataForSEO 키 없음")
        return 1
    auth = base64.b64encode(f"{login}:{pw}".encode()).decode()
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["geo", "brand", "keyword", "month", "searches"])
    labs = pd.read_csv(DATA / "absvol_monthly.csv")
    rows, cost = [], 0.0
    for geo in geos:
        if geo not in codes:
            print(f"  {geo}: 코드 없음 (absvol_meta.json 확인)")
            continue
        loc, lang = codes[geo]
        k2b = {kw: b for b in BRANDS for kw in keywords_for(b, geo)}
        js = None
        for attempt in range(3):
            try:
                r = requests.post(API, json=[{"keywords": list(k2b), "location_code": loc, "language_code": lang}],
                                  headers={"Authorization": "Basic " + auth}, timeout=90)
                r.raise_for_status()
                js = r.json()
                break
            except Exception as e:
                print(f"  {geo}: {type(e).__name__} 재시도 {attempt + 1}/3")
                time.sleep(15)
        if js is None:
            continue
        task = (js.get("tasks") or [{}])[0]
        if task.get("status_code") != 20000:
            print(f"  {geo}: API 오류 {task.get('status_message')}")
            continue
        n0 = len(rows)
        for it in task.get("result") or []:
            kw = it.get("keyword", "")
            for m in it.get("monthly_searches") or []:
                rows.append({"geo": geo, "brand": k2b.get(kw, kw), "keyword": kw,
                             "month": f"{m['year']}-{m['month']:02d}", "searches": m.get("search_volume") or 0})
        cost += js.get("cost") or 0
        new = pd.DataFrame(rows[n0:])
        # 검산: 본 데이터(labs)와 겹치는 가장 최근 달에서 브랜드 합이 같은가
        lb = labs[labs["geo"] == geo]
        common = sorted(set(new["month"]) & set(lb["month"]))
        note = ""
        if common:
            mo = common[-1]
            a = new[new["month"] == mo].groupby("brand")["searches"].sum()
            b = lb[lb["month"] == mo].groupby("brand")["searches"].sum()
            j = pd.concat([a, b], axis=1, keys=["gads", "labs"]).dropna()
            same = (j["gads"] == j["labs"]).mean() if len(j) else float("nan")
            note = f" · 검산 {mo}: 브랜드 {len(j)}개 중 값이 똑같은 비율 {same:.0%}"
        print(f"  {geo}: {len(new)}행 · {new['month'].min()}~{new['month'].max()} · 비용 ${js.get('cost')}{note}")
    if not rows:
        print("받은 것 없음")
        return 1
    new = pd.DataFrame(rows)
    keep = old[~old["geo"].isin(set(new["geo"]))]
    allr = pd.concat([keep, new], ignore_index=True).sort_values(["geo", "brand", "keyword", "month"])
    allr.to_csv(OUT, index=False, encoding="utf-8")
    META.write_text(json.dumps({"fetched": dt.datetime.now().isoformat(timespec="seconds"),
                                "geos": sorted(set(allr["geo"])), "months": [allr["month"].min(), allr["month"].max()],
                                "cost_usd_this_run": round(cost, 4),
                                "source": "DataForSEO keywords_data/google_ads/search_volume (12개월, 나라별)"},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: {len(allr)}행 · 이번 실행 비용 ${cost:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
