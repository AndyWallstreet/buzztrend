# -*- coding: utf-8 -*-
"""절대검색량 '아직 안 나온 달' 을 구글 트렌드로 추정 — DataForSEO(구글애즈) 가 늦을 때의 3순위 출처.

왜 (PM 2026-11-11): 구글애즈 월 검색수는 다음 달 15~20일에야 나온다. 구글 트렌드는 지연이 없지만
    상대지수(최대=100)라 그대로는 못 쓴다. 그래서
        10월 추정 = 9월 절대량(구글애즈 실측) x (트렌드 10월 평균 / 트렌드 9월 평균)
    같은 시리즈 안의 비율이라 상대지수여도 괜찮다. 구글애즈 실측이 들어오면 이 추정은 자동으로 버려진다
    (absvol_nowcast.combined 가 실측 우선).

방식
  - 나라별로 브랜드를 9월 절대량 크기순으로 5개씩 묶어 한 번에 받는다 (작은 브랜드가 큰 브랜드 옆에서 0 으로
    눌리는 것을 줄이려고). 카테고리 0(전체) = 구글애즈와 같은 기준.
  - 주간 값을 주 시작일의 달로 묶어 월평균 → 비율. 9월 평균이 2 미만이면 해상도가 없어 추정 안 함.
  - 브랜드에 검색어가 여러 개면(센텔리안 '*' 2개 등) 대표 검색어 1개로 비율을 구해 모든 검색어 행에 곱한다.

산출: data/cosmetics/absvol_trends_est.csv (geo, brand, keyword, month, searches, ratio, t_prev, t_now,
      base_month, base_searches, fetched) · absvol_trends_est_meta.json
Usage: python absvol_trends_est.py [--geos US JP] [--force]
"""
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

from absvol_nowcast import combined
from cosmetics_absvol_update import DATA, keywords_for
from gtrends import fetch_trends

OUT = DATA / "absvol_trends_est.csv"
META = DATA / "absvol_trends_est_meta.json"
DELAY = float(os.environ.get("TRENDS_DELAY", "4"))   # 429 가 나면 TRENDS_DELAY=12 로 다시


def _load(name):
    p = DATA / name
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    geos_arg = argv[argv.index("--geos") + 1:] if "--geos" in argv else None
    today = dt.date.today()
    target = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")     # 지난달
    base = combined(_load("absvol_monthly.csv"), _load("absvol_gads.csv"))
    base = base[(base["geo"] != "WW") & (base["searches"] < 1_000_000)]
    last_by_key = base.groupby(["geo", "brand", "keyword"])["month"].max()
    if last_by_key.min() >= target and not force:
        print(f"실측이 이미 {target} 까지 있음 — 추정 불필요")
        return 0
    if META.exists() and not force and not geos_arg:
        meta = json.loads(META.read_text(encoding="utf-8"))
        age = (today - dt.date.fromisoformat(meta["fetched"][:10])).days
        if meta.get("target") == target and not meta.get("failed") and age < 7:
            print(f"{target} 추정 {meta['fetched'][:10]} 에 이미 받음 — 7일 뒤 다시 (구글 429 방지). 지금 꼭 받으려면 --force")
            return 0
    base_month = last_by_key.max()                                              # 보통 지난달의 전달
    geos = geos_arg or sorted(base["geo"].unique())
    old = pd.read_csv(OUT, encoding="utf-8-sig") if OUT.exists() else pd.DataFrame()
    rows, failed = [], []
    for geo in geos:
        bgeo = base[(base["geo"] == geo) & (base["month"] == base_month)]
        size = bgeo.groupby("brand")["searches"].sum().sort_values(ascending=False)
        if not len(size):
            continue
        brands = list(size.index)
        chunks = [brands[i:i + 5] for i in range(0, len(brands), 5)]
        for ch in chunks:
            kw = {keywords_for(b, geo)[0]: b for b in ch}
            df = None
            for attempt in range(3):
                try:
                    df = fetch_trends(list(kw), geo=geo, timeframe="today 12-m", category=0)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  {geo} {ch[0]}..: {type(e).__name__} 시도 {attempt + 1}/3")
                    time.sleep(90 * (attempt + 1))        # 429 뒤 90s, 180s, 270s
            if df is None:
                failed.append((geo, ch))
                continue
            df["m"] = df["date"].str[:7]
            mo = df.groupby(["keyword", "m"])["value"].mean().unstack()
            for k, b in kw.items():
                if k not in mo.index or target not in mo.columns or base_month not in mo.columns:
                    continue
                t_prev, t_now = float(mo.loc[k, base_month]), float(mo.loc[k, target])
                if t_prev < 2:          # 트렌드 해상도 없음(0~1) → 추정 안 함
                    continue
                ratio = t_now / t_prev
                for _, r in bgeo[bgeo["brand"] == b].iterrows():
                    rows.append({"geo": geo, "brand": b, "keyword": r["keyword"], "month": target,
                                 "searches": int(round(r["searches"] * ratio)), "ratio": round(ratio, 4),
                                 "t_prev": round(t_prev, 2), "t_now": round(t_now, 2),
                                 "base_month": base_month, "base_searches": int(r["searches"]),
                                 "fetched": today.isoformat()})
            time.sleep(DELAY)
        n = sum(1 for r in rows if r["geo"] == geo)
        print(f"  {geo}: {n}행 추정 ({base_month} 실측 x 트렌드 {target}/{base_month})")
    if not rows:
        print("추정 결과 없음")
        return 1
    new = pd.DataFrame(rows)
    if len(old):
        keep = old[~(old["geo"].isin(set(new["geo"])) & (old["month"] == target))]
        new = pd.concat([keep, new], ignore_index=True)
    new = new.sort_values(["geo", "brand", "keyword", "month"])
    new.to_csv(OUT, index=False, encoding="utf-8")
    META.write_text(json.dumps({"fetched": dt.datetime.now().isoformat(timespec="seconds"),
                                "target": target, "base_month": base_month,
                                "geos": sorted(set(new["geo"])), "failed": [f"{g}:{c[0]}" for g, c in failed],
                                "source": "Google Trends weekly (category 0) x DataForSEO base month"},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: {len(new)}행 · 실패 {len(failed)}묶음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
