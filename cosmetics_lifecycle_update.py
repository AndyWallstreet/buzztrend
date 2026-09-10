# -*- coding: utf-8 -*-
"""K뷰티 브랜드 수명주기 데이터 — 브랜드별 구글 트렌드 5년치 (나라별).

Usage:
    python cosmetics_lifecycle_update.py [US JP ...]   # 생략 시 US JP

산출물 (data/cosmetics/):
    gtrends_life_{geo}.csv   date,brand,keyword,value — 브랜드별 '단독' 5년 주간
    gtrends_life_meta.json

- 브랜드마다 단독 쿼리(자기 피크=100)라 브랜드끼리 크기 비교는 안 됨 —
  화면에서 '자기 피크 대비 %'로 정규화해 모양(수명주기 단계)만 비교한다.
- 일본은 가타카나로 검색하므로 JP 키워드는 별도 매핑. (?) 표시는 표기 불확실.
- 요청이 많아(브랜드 18개×나라) 429가 나면 90초 쉬고 재시도, 그래도 실패면
  그 브랜드만 건너뛰고 기존 값 유지. 주 1회 갱신이면 충분.
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd

from gtrends import fetch_trends

DATA = Path(__file__).resolve().parent / "data" / "cosmetics"
CATEGORY = 44                            # Beauty & Fitness
TIMEFRAME = "today 5-y"

# brand -> geo별 검색어 ("*"=기본). 일본은 가타카나 우세.
BRANDS = {
    "madeca cream": {"*": "madeca cream", "JP": "マデカクリーム"},
    "reedle shot": {"*": "reedle shot", "JP": "リードルショット"},
    "medicube": {"*": "medicube", "JP": "メディキューブ"},
    "anua": {"*": "anua", "JP": "アヌア"},
    "cosrx": {"*": "cosrx", "JP": "コスアールエックス"},
    "tirtir": {"*": "tirtir", "JP": "ティルティル"},
    "beauty of joseon": {"*": "beauty of joseon"},
    "torriden": {"*": "torriden", "JP": "トリデン"},
    "skin1004": {"*": "skin1004", "JP": "スキン1004"},
    "round lab": {"*": "round lab", "JP": "ラウンドラボ"},
    "biodance": {"*": "biodance", "JP": "バイオダンス"},
    "d'alba": {"*": "d'alba", "JP": "ダルバ"},
    "manyo": {"*": "manyo", "JP": "魔女工場"},
    "mixsoon": {"*": "mixsoon", "JP": "ミクスン"},
    "numbuzin": {"*": "numbuzin", "JP": "ナンバーズイン"},
    "abib": {"*": "abib", "JP": "アビブ"},
    "isntree": {"*": "isntree", "JP": "イズントゥリー"},
    "laneige": {"*": "laneige", "JP": "ラネージュ"},
}


def collect(geo):
    out_p = DATA / f"gtrends_life_{geo}.csv"
    old = pd.read_csv(out_p) if out_p.exists() else pd.DataFrame(
        columns=["date", "brand", "keyword", "value"])
    frames, ok, fail = [], [], []
    for brand, kwmap in BRANDS.items():
        kw = kwmap.get(geo, kwmap["*"])
        df = None
        for attempt in range(3):
            try:
                df = fetch_trends([kw], geo=geo, timeframe=TIMEFRAME,
                                  category=CATEGORY)
                break
            except Exception as e:
                print(f"  {geo}/{brand}: {type(e).__name__} "
                      f"(시도 {attempt + 1}/3)")
                time.sleep(90)
        if df is None:
            fail.append(brand)
            continue
        df["brand"] = brand
        df["keyword"] = kw
        frames.append(df[["date", "brand", "keyword", "value"]])
        ok.append(brand)
        print(f"  {geo}/{brand}: {len(df)}주, 최신 "
              f"{df['value'].iloc[-1]}")
        time.sleep(10)
    if frames:
        new = pd.concat(frames)
        keep = old[~old["brand"].isin(ok)]        # 실패 브랜드는 기존값 유지
        pd.concat([keep, new]).to_csv(out_p, index=False, encoding="utf-8")
        print(f"{out_p.name}: 성공 {len(ok)} / 실패 {len(fail)} {fail}")
    else:
        print(f"{geo}: 전부 실패, 기존 파일 유지")
    return ok, fail


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    geos = sys.argv[1:] or ["US", "JP"]
    result = {}
    for geo in geos:
        print(f"== {geo} ==")
        ok, fail = collect(geo)
        result[geo] = {"ok": len(ok), "fail": fail}
        time.sleep(15)
    meta_p = DATA / "gtrends_life_meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta.update({
        "fetched": dt.datetime.now().isoformat(timespec="seconds"),
        "timeframe": TIMEFRAME, "category": CATEGORY,
        "geos": sorted(set(list(meta.get("geos", [])) + geos)),
        "last_run": result,
        "jp_uncertain": ["mixsoon"],
    })
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                      encoding="utf-8")


if __name__ == "__main__":
    main()
