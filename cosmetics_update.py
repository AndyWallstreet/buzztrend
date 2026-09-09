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

from gtrends import fetch_trends

DATA = Path(__file__).resolve().parent / "data" / "cosmetics"

# 묶음별로 나눠 받는다 (상대값이라 묶음 안에서만 비교 가능):
#  solo     — 센텔리안 자체 추세 (큰 브랜드와 같이 넣으면 상대값이 0으로 눌림)
#  compare  — K뷰티 브랜드 간 검색 점유 비교 (상대 스케일 공유)
#  solo_5y  — solo와 같은 키워드의 5년치 (YoY 증가율 계산용, 주간→월 집계)
SETS = {"solo": ("today 12-m", ["centellian24", "madeca cream"]),
        "compare": ("today 12-m", ["centellian24", "medicube", "anua", "cosrx"]),
        "solo_5y": ("today 5-y", ["centellian24", "madeca cream"])}
GEO = "US"


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    ok = []
    for name, (tf, kws) in SETS.items():
        try:
            df = fetch_trends(kws, geo=GEO, timeframe=tf)
        except Exception as e:
            print(f"구글 트렌드 '{name}' 수집 실패 ({type(e).__name__}) — "
                  "기존 데이터 유지, 다음 배치에서 재시도")
            continue
        df.to_csv(DATA / f"gtrends_{name}.csv", index=False, encoding="utf-8")
        last = df[df["date"] == df["date"].max()].set_index("keyword")["value"]
        print(f"gtrends_{name}.csv: {df['date'].nunique()}개 시점 | 최신 "
              f"centellian24={last.get('centellian24', '—')}")
        ok.append(name)
        time.sleep(3)
    if ok:
        (DATA / "gtrends_meta.json").write_text(json.dumps(
            {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
             "geo": GEO, "sets": {k: v[1] for k, v in SETS.items()}},
            ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
