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
Usage: python absvol_trends_est.py [--geos US JP] [--force] [--target 2026-11] [--fill]
  --fill: 이미 추정된 브랜드는 두고 빠진 브랜드만 요청 (429 로 끊긴 뒤 이어받기). 나라마다 끝나면 바로 저장.
  --target 가 이번 달이면 "월중 추정": 지금까지 나온 주간 값만 평균 (PM 2026-11-20, 11월 중순에 11월 방향 보기).
  2026-11-16 실전 채점: 10월 추정은 오차 중앙값 24%, 큰 점프(행사) 달은 못 잡음. 트렌드 지수 5 미만은 제외 (백테스트 결과).
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
GEO_PAUSE = float(os.environ.get("TRENDS_GEO_PAUSE", "0"))   # 나라 사이 쉬는 시간(초) — 2026-11-20 전체 실행은 60 권장


def _load(name):
    p = DATA / name
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    fill = "--fill" in argv          # 이미 추정된 브랜드는 건너뛰고 빠진 브랜드만 채움 (429 로 끊긴 뒤 이어받기)
    geos_arg = None
    if "--geos" in argv:
        geos_arg = []
        for a in argv[argv.index("--geos") + 1:]:
            if a.startswith("--"):
                break
            geos_arg.append(a)
    today = dt.date.today()
    target = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")     # 지난달
    if "--target" in argv:
        target = argv[argv.index("--target") + 1]
    partial = target == today.strftime("%Y-%m")                                  # 이번 달 = 월중 추정
    base = combined(_load("absvol_monthly.csv"), _load("absvol_gads.csv"))
    base = base[(base["geo"] != "WW") & (base["searches"] < 1_000_000)]
    last_by_key = base.groupby(["geo", "brand", "keyword"])["month"].max()
    if last_by_key.min() >= target and not force:
        if "--target" in argv or today.day < 10:
            print(f"실측이 이미 {target} 까지 있음 — 추정 불필요")
            return 0
        # 지난달 실측이 들어온 뒤(매달 10일~) 에는 이번 달 '월중 추정' 으로 넘어감 — 7일마다 갱신 (PM 2026-11-20)
        target = today.strftime("%Y-%m")
        partial = True
        print(f"지난달 실측 있음 → 이번 달 {target} 월중 추정으로 전환")
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

    def save_geo(geo, grows):
        """나라 하나 끝날 때마다 바로 저장 — 구글 429 로 중간에 죽어도 받은 건 남김 (2026-11-20 두 번 날린 뒤)."""
        nonlocal old
        new = pd.DataFrame(grows)
        if len(old) and len(new):
            drop = (old["geo"] == geo) & (old["month"] == target)
            if fill:
                drop &= old["brand"].isin(set(new["brand"]))
            old = old[~drop]
        if len(new):
            old = pd.concat([old, new], ignore_index=True).sort_values(["geo", "brand", "keyword", "month"])
            old.to_csv(OUT, index=False, encoding="utf-8")
        tgt = old[old["month"] == target] if len(old) else pd.DataFrame()
        META.write_text(json.dumps({"fetched": dt.datetime.now().isoformat(timespec="seconds"),
                                    "target": target, "base_month": base_month, "partial": partial,
                                    "through": (str(tgt["through"].dropna().max()) if partial and len(tgt) and "through" in tgt else ""),
                                    "geos": sorted(set(tgt["geo"])) if len(tgt) else [],
                                    "failed": [f"{g}:{c[0]}" for g, c in failed],
                                    "source": "Google Trends weekly (category 0) x DataForSEO base month"},
                                   ensure_ascii=False, indent=1), encoding="utf-8")

    for geo in geos:
        bgeo = base[(base["geo"] == geo) & (base["month"] == base_month)]
        size = bgeo.groupby("brand")["searches"].sum().sort_values(ascending=False)
        if not len(size):
            continue
        have = set(old.loc[(old["geo"] == geo) & (old["month"] == target), "brand"]) if fill and len(old) else set()
        pending = [b for b in size.index if b not in have]
        if fill and have:
            print(f"  {geo}: 이미 {len(have)}개 있음 → 빠진 {len(pending)}개만 요청", flush=True)
        grows = []
        # 트렌드 지수는 '같은 요청 안에서 제일 큰 브랜드' 기준 0~100 이라, 큰 브랜드와 묶이면 작은 브랜드는 지수 2~4 로 눌려
        # 비율을 못 읽음 (2026-11 미국: medicube 가 89 까지 뛰자 madeca cream 이 지수 2 로 빠짐).
        # 1라운드: 큰 순서로 5개 묶음 → 지수 <5 인 브랜드는 2라운드에서 작은 것들끼리 다시 묶음 → 그래도 <5 면 3라운드 단독 요청.
        for rnd in range(3):
            if not pending:
                break
            chunks = [pending[i:i + 5] for i in range(0, len(pending), 5)] if rnd < 2 else [[b] for b in pending]
            pending = []
            for ch in chunks:
                kw = {keywords_for(b, geo)[0]: b for b in ch}
                df = None
                for attempt in range(3):
                    try:
                        df = fetch_trends(list(kw), geo=geo, timeframe="today 12-m", category=0)
                        break
                    except Exception as e:  # noqa: BLE001
                        print(f"  {geo} {ch[0]}..: {type(e).__name__} 시도 {attempt + 1}/3", flush=True)
                        time.sleep((120, 300, 600)[attempt])  # 429 뒤 2분, 5분, 10분 — 구글 차단은 몇 분 이어짐 (90/180/270 은 부족했음)
                if df is None or len(df) == 0 or "date" not in df.columns:
                    if df is not None:
                        print(f"  {geo} {ch[0]}: 트렌드 데이터 없음(검색량 너무 적음) → 건너뜀", flush=True)
                    else:
                        failed.append((geo, ch))
                    continue
                df["m"] = df["date"].str[:7]
                df = df[df["date"] <= today.isoformat()]                 # 월중: 아직 안 온 주(값 0) 는 뺌
                through = df.loc[df["m"] == target, "date"].max() if partial else None
                n_weeks = int((df["m"] == target).sum() // max(len(kw), 1))
                mo = df.groupby(["keyword", "m"])["value"].mean().unstack()
                for k, b in kw.items():
                    if k not in mo.index or target not in mo.columns or base_month not in mo.columns:
                        continue
                    t_prev, t_now = float(mo.loc[k, base_month]), float(mo.loc[k, target])
                    if t_prev < 5:          # 해상도 없음 (백테스트: 지수<5 는 오차 21~38%, 방향 30%) → 다음 라운드로
                        if rnd < 2:
                            pending.append(b)
                        continue
                    ratio = t_now / t_prev
                    for _, r in bgeo[bgeo["brand"] == b].iterrows():
                        grows.append({"geo": geo, "brand": b, "keyword": r["keyword"], "month": target,
                                     "searches": int(round(r["searches"] * ratio)), "ratio": round(ratio, 4),
                                     "t_prev": round(t_prev, 2), "t_now": round(t_now, 2),
                                     "base_month": base_month, "base_searches": int(r["searches"]),
                                     "fetched": today.isoformat(), "partial": partial,
                                     "through": through or "", "weeks": n_weeks, "round": rnd + 1})
                time.sleep(DELAY)
            if pending:
                print(f"  {geo}: 지수<5 로 눌린 {len(pending)}개 → {rnd + 2}라운드 재요청", flush=True)
        rows.extend(grows)
        save_geo(geo, grows)
        print(f"  {geo}: {len(grows)}행 추정 ({base_month} 실측 x 트렌드 {target}/{base_month}) · 저장", flush=True)
        time.sleep(GEO_PAUSE)
    if not rows:
        print("추정 결과 없음")
        return 1
    print(f"{OUT.name}: {len(old)}행 (이번 실행 {len(rows)}행) · 실패 {len(failed)}묶음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
