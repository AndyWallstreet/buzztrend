# -*- coding: utf-8 -*-
"""Cosmetics/Beauty 섹터 — 구글 트렌드 일일 수집 (센텔리안24 외 K뷰티 브랜드).

Usage:
    python cosmetics_update.py

산출물 (data/cosmetics/):
    gtrends_us.csv   미국 구글 검색 관심도 (주간, 12개월 롤링, 브랜드 비교 상대값)
    gtrends_meta.json

- 구글 트렌드 값은 기간·키워드 조합 안에서의 상대값(최대=100)이라, 매 실행마다
  12개월 전체를 다시 받아 통째로 교체한다 (누적 append 아님).
- 429(요청 과다)면 이번 회차는 건너뛰고 기존 데이터 유지 — 일배치 재시도로 충분.
- 아마존은 약관상 자동 수집 금지 (kbeauty/docs/ACCESS_REVIEW.md) → 수동 스냅샷
  (data/cosmetics/manual_amazon.csv) 또는 Keepa API 구독으로만.
"""
import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

DATA = Path(__file__).resolve().parent / "data" / "cosmetics"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Referer": "https://trends.google.com/trends/explore"}

# 두 묶음으로 나눠 받는다:
#  solo    — 센텔리안 자체 추세 (큰 브랜드와 같이 넣으면 상대값이 0으로 눌림)
#  compare — K뷰티 브랜드 간 검색 점유 비교 (상대 스케일 공유)
SETS = {"solo": ["centellian24", "madeca cream"],
        "compare": ["centellian24", "medicube", "anua", "cosrx"]}
GEO = "US"
TIMEFRAME = "today 12-m"


def fetch_trends(keywords) -> pd.DataFrame:
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://trends.google.com/trends/?geo=US", timeout=20)   # NID 쿠키
    time.sleep(1.5)
    req = {"comparisonItem": [{"keyword": k, "geo": GEO, "time": TIMEFRAME}
                              for k in keywords],
           "category": 0, "property": ""}
    r = s.get("https://trends.google.com/trends/api/explore",
              params={"hl": "en-US", "tz": "-540", "req": json.dumps(req)},
              timeout=30)
    r.raise_for_status()
    widgets = json.loads(r.text[5:])["widgets"]
    w = next(x for x in widgets if x["id"] == "TIMESERIES")
    time.sleep(1.5)
    r2 = s.get("https://trends.google.com/trends/api/widgetdata/multiline",
               params={"hl": "en-US", "tz": "-540",
                       "req": json.dumps(w["request"]), "token": w["token"]},
               timeout=30)
    r2.raise_for_status()
    data = json.loads(r2.text[5:])["default"]["timelineData"]
    rows = []
    for d in data:
        day = dt.datetime.fromtimestamp(int(d["time"])).date().isoformat()
        for k, v in zip(keywords, d["value"]):
            rows.append({"date": day, "keyword": k, "value": v})
    return pd.DataFrame(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    ok = []
    for name, kws in SETS.items():
        try:
            df = fetch_trends(kws)
        except Exception as e:
            print(f"구글 트렌드 '{name}' 수집 실패 ({type(e).__name__}) — "
                  "기존 데이터 유지, 다음 배치에서 재시도")
            continue
        df.to_csv(DATA / f"gtrends_{name}.csv", index=False, encoding="utf-8")
        last = df[df["date"] == df["date"].max()].set_index("keyword")["value"]
        print(f"gtrends_{name}.csv: {df['date'].nunique()}주 | 최신 주 "
              f"centellian24={last.get('centellian24', '—')}")
        ok.append(name)
        time.sleep(3)
    if ok:
        (DATA / "gtrends_meta.json").write_text(json.dumps(
            {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
             "geo": GEO, "timeframe": TIMEFRAME, "sets": SETS},
            ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
