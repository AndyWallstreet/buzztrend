# -*- coding: utf-8 -*-
"""구글 트렌드 직접 호출 공용 모듈 (pytrends 미사용 — 429 차단으로 폐기).

cosmetics_update.py(일배치)와 app_pages/cosmetics.py(사이트 검색)가 같이 쓴다.
흐름: ①세션으로 /trends 열어 NID 쿠키 확보 ②explore로 TIMESERIES 토큰
③widgetdata/multiline → ")]}'" 5자 프리픽스 절단 후 JSON.
주의: 값은 '해당 키워드 묶음+기간 안에서의 상대값(최대=100)' — 묶음이 다르면
값을 서로 비교할 수 없다. 클라우드 서버 IP는 429가 잦음(로컬은 잘 됨).
"""
import datetime as dt
import json
import time

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Referer": "https://trends.google.com/trends/explore"}


def fetch_trends(keywords, geo="US", timeframe="today 12-m",
                 category=0) -> pd.DataFrame:
    """키워드 리스트(최대 5개) → date/keyword/value 롱 포맷 DataFrame.

    category: 구글 트렌드 카테고리 필터 (0=전체, 44=Beauty & Fitness).
    """
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://trends.google.com/trends/?geo=US", timeout=20)   # NID 쿠키
    time.sleep(1.5)
    req = {"comparisonItem": [{"keyword": k, "geo": geo, "time": timeframe}
                              for k in keywords],
           "category": category, "property": ""}
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
