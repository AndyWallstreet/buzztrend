# -*- coding: utf-8 -*-
"""K뷰티 브랜드별 아마존 BSR 과거 이력 — Keepa API.

왜: 퍼널(상대검색 → 절대검색 → BSR → 매출)에서 매출 점이 너무 적다.
    비상장 브랜드는 연 1회 공시라 브랜드당 3~6점뿐이고, 18개 중 12개는
    상관 계산 자체가 안 된다. BSR 은 일간이라 브랜드당 수백 점이 생긴다.
    BSR 이 매출 대리 지표로 쓸 만한지 먼저 확인하고, 되면 공시가 드문
    브랜드(센텔리안24 포함)를 주간으로 추적한다.

Usage:
    python keepa_bsr_history.py --discover        # 브랜드 → ASIN 찾기 (브랜드당 10토큰)
    python keepa_bsr_history.py                   # BSR 이력 받기 (ASIN당 1토큰)
    python keepa_bsr_history.py --brand cosrx     # 한 브랜드만
    python keepa_bsr_history.py --domain 5        # 일본 아마존 (기본 1 = 미국)

키: 환경변수 KEEPA_KEY 또는 .streamlit/secrets.toml 의 [keepa] key
    (secrets.toml 은 gitignore — 절대 커밋하지 말 것)

산출 (data/cosmetics/):
    bsr_asins{suffix}.csv     brand,asin,title   ← --discover 결과, 손으로 고쳐도 됨
    bsr_daily{suffix}.csv     brand,asin,date,bsr
    bsr_monthly{suffix}.csv   brand,month,bsr_median,bsr_strength,n_asin
    bsr_meta{suffix}.json

주의: BSR 은 숫자가 작을수록 잘 팔린다. 그대로 쓰면 상관 부호가 뒤집혀 읽기 어렵다.
      그래서 bsr_strength = -log10(BSR) 을 같이 저장한다 (클수록 잘 팔림).

토큰(Starter 20/분 = 월 892,800 기준): 최초 수집 약 234, 주간 추적 월 약 216.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
META_URL = "https://api.keepa.com"
I_SALES = 3                       # csv[3] = SALES rank
# Keepa 시간 = (unix_ms / 60000) - 21564000  →  unix_ms = (분 + 21564000) * 60000.
# 21564000 은 '분' 단위다. ms 로 더하려면 x60000 해야 한다 — 이걸 빠뜨려서
# 날짜가 1974년으로 나왔다(2026-10-15).
KEEPA_EPOCH_MS = 21564000 * 60000      # = 1,293,840,000,000 (2011-01-01 UTC)
DOMAINS = {1: "us", 5: "jp", 3: "uk", 4: "de"}

# funnel_study.MAP 과 같은 브랜드. 값 = 아마존에 등록된 브랜드명.
BRANDS = {
    "madeca cream": "Centellian 24", "reedle shot": "VT", "atopalm": "Atopalm",
    "medicube": "medicube", "d'alba": "d'Alba", "manyo": "Manyo",
    "laneige": "LANEIGE", "anua": "Anua", "cosrx": "COSRX",
    "skin1004": "SKIN1004", "beauty of joseon": "Beauty of Joseon",
    "tirtir": "TIRTIR", "torriden": "TORRIDEN", "numbuzin": "numbuzin",
    "round lab": "Round Lab", "abib": "Abib", "mixsoon": "mixsoon",
    "biodance": "BIODANCE",
}
TOP_N = 3            # 브랜드당 대표 ASIN 수 (많이 팔리는 순)

# 제목 검사: 상품명에 이 단어 중 하나도 없으면 그 상품은 버린다 (대소문자 무시).
# 브랜드명 검색이 엉뚱한 상품을 물어온 적이 있다 (2026-10-15):
#   VT → USB 헤드셋 (미국·일본 둘 다), d'Alba → 슬라임 장난감·주방용품,
#   Manyo → 일본 이쑤시개. 제품명 검색으로 고쳤고, 이 검사로 재발을 막는다.
TITLE_OK = {
    "madeca cream": ["centellian", "センテリアン"], "reedle shot": ["reedle", "リードル"],
    "atopalm": ["atopalm", "アトパーム"], "medicube": ["medicube", "メディキューブ"],
    # d'alba: 'd'alba'·'ダルバ' 만 보면 오페라 음반·이탈리아 와인(Barbera d'Alba)도 통과한다
    "d'alba": ["truffle", "トリュフ", "d'alba公式", "(d'alba)"],
    "manyo": ["ma:nyo", "manyo factory", "魔女工場"],
    "laneige": ["laneige", "ラネージュ"], "anua": ["anua", "アヌア"], "cosrx": ["cosrx"],
    "skin1004": ["skin1004"], "beauty of joseon": ["beauty of joseon", "boj"],
    "tirtir": ["tirtir"], "torriden": ["torriden", "トリデン"],
    "numbuzin": ["numbuzin", "ナンバーズイン"], "round lab": ["round lab", "ラウンドラボ"],
    "abib": ["abib"], "mixsoon": ["mixsoon", "ミクスン"], "biodance": ["biodance", "バイオダンス"],
}


def title_ok(brand, title):
    words = TITLE_OK.get(brand)
    if not words:
        return True
    t = (title or "").lower()
    return any(w.lower() in t for w in words)


def paths(domain):
    sfx = "" if domain == 1 else "_" + DOMAINS.get(domain, str(domain))
    return (DATA / f"bsr_asins{sfx}.csv", DATA / f"bsr_daily{sfx}.csv",
            DATA / f"bsr_monthly{sfx}.csv", DATA / f"bsr_meta{sfx}.json")


def _key():
    k = os.environ.get("KEEPA_KEY")
    if k:
        return k.strip()
    sec = ROOT / ".streamlit" / "secrets.toml"
    if sec.exists():
        import tomllib
        return (tomllib.loads(sec.read_text(encoding="utf-8"))
                .get("keepa", {}).get("key"))
    return None


def _call(path, key, body=None, **params):
    """429(토큰 소진)면 Keepa 가 알려주는 만큼 기다렸다 재시도. 밤새 돌려도 되게.
    body 가 있으면 POST (Product Finder 는 POST 전용).

    주의: 예외 메시지에 요청 URL 을 그대로 넣으면 키가 로그에 남는다.
    실제로 한 번 유출됐다(2026-10-15) — 반드시 키를 지우고 올린다."""
    for attempt in range(60):
        params["key"] = key
        if body is None:
            r = requests.get(f"{META_URL}/{path}", params=params, timeout=120)
        else:
            r = requests.post(f"{META_URL}/{path}", params=params, json=body,
                              timeout=120)
        if r.status_code == 429:
            wait = ((r.json() or {}).get("refillIn") or 60000) / 1000 + 2
            print(f"    토큰 소진 — {wait:.0f}초 대기 ({attempt + 1}회차)")
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} "
                               + r.text[:200].replace(key, "<KEY>"))
        js = r.json()
        if js.get("error"):
            raise RuntimeError(str(js["error"]).replace(key, "<KEY>"))
        return js
    raise RuntimeError("토큰 대기 60회 초과")


def discover(key, domain):
    """Product Finder 로 브랜드별 대표 ASIN 찾기. 브랜드당 10토큰."""
    asins_csv = paths(domain)[0]
    rows = []
    for b, brand_name in BRANDS.items():
        print(f"  {b:18s} <- 브랜드 '{brand_name}'")
        # perPage 는 50 미만이면 400 ("too small") — 50 받아서 앞에서 TOP_N 만 쓴다.
        # current_SALES_gte=1 은 순위 없는(=안 팔리는) 상품을 뺀다.
        sel = {"brand": [brand_name.lower()], "current_SALES_gte": 1,
               "sort": [["current_SALES", "asc"]], "perPage": 50, "page": 0}
        try:
            js = _call("query", key, body=sel, domain=domain)
        except Exception as e:
            print(f"    실패: {e}")
            continue
        found = (js.get("asinList") or [])[:TOP_N]
        if not found:
            print("    결과 없음 — bsr_asins.csv 에 손으로 넣어야 함")
            continue
        for a in found:
            rows.append({"brand": b, "asin": a, "title": ""})
        print(f"    {len(found)}개: {', '.join(found)}")
    DATA.mkdir(parents=True, exist_ok=True)
    with asins_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "title"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n{asins_csv.name}: {len(rows)}개 ASIN "
          f"({len({r['brand'] for r in rows})}개 브랜드)")
    return rows


# 순위 → 판매량 환산: 판매량 ∝ 순위^-SALES_EXP (가정). 업계 추정식은 대체로 0.7~1.0 사이.
# 1,000위 상품 하나가 파는 양 = 1 이 되도록 맞춘다 (단위 없는 상대 지수).
SALES_EXP = 0.85
SALES_REF = 1000


def sales_params(domain):
    """시장별 지수와 '1,000위 상품의 월 판매 개수'. keepa_sales_calib.py 가 아마존 '지난달 X개
    이상 구매' 표시로 직접 맞춘 값을 쓴다 (2026-10-15: 미국 0.66 · 일본 0.57 — 처음 가정 0.85 는
    책 카테고리 연구값이라 뷰티에는 너무 가팔랐다). 파일이 없으면 예전 가정으로."""
    p = DATA / "bsr_calib.json"
    mk = DOMAINS.get(domain, "us").upper()
    if p.exists():
        c = json.loads(p.read_text(encoding="utf-8")).get(mk)
        if c:
            return float(c["exponent"]), float(c["sold_at_rank_1000"])
    return SALES_EXP, float("nan")


def aggregate(domain):
    """일별 BSR → 월별 브랜드 지표 3종. Keepa 를 다시 부르지 않는다 (토큰 0).

    bsr_median  기존 방식: 상품별 월 중앙값 → 상품끼리 중앙값.
                약점: 순위 낮은 신상품이 들어오면 브랜드 선이 급락한다
                (코스알엑스 2023-05: 주력 세럼 8위인데 신규 세트 67만 위 → 브랜드 34만 위).
    best_rank   ② 주력 상품 순위: 그 달 가장 잘 팔린 상품의 월 중앙 순위.
    sales_idx   ① 추정 판매량 합계: 일별 순위를 판매량 지수로 바꿔 상품끼리 더한다.
                신상품은 판매량을 더할 뿐 선을 끌어내리지 않는다.
                같은 날 같은 순위인 상품은 한 상품 페이지로 묶인 것(순위 공유)이라 한 번만 센다.
    strength 열은 퍼널용 로그값 — 셋 다 '클수록 잘 팔림' 으로 맞춘다.
    """
    import numpy as np
    import pandas as pd
    _a, daily, monthly, _m = paths(domain)
    sfx = monthly.stem.replace("bsr_monthly", "")
    asin_monthly = DATA / f"bsr_asin_monthly{sfx}.csv"
    d = pd.read_csv(daily)
    d["month"] = d["date"].str[:7]
    # 하루에 여러 번 바뀐 순위 → 그날 중앙값
    day = d.groupby(["brand", "asin", "date"], as_index=False)["bsr"].median()
    # Keepa 는 순위가 '바뀐 날' 만 기록한다. 순위는 다음 변화까지 유지되므로 빈 날을 앞 값으로
    # 채운다 (최대 14일 — 그보다 길게 비면 품절·순위 없음일 수 있어 채우지 않음).
    # 이렇게 해야 상품끼리 같은 날을 비교할 수 있고, 월 평균도 날짜 가중이 된다.
    filled = []
    for (b, a_), g_ in day.groupby(["brand", "asin"]):
        s_ = g_.set_index(pd.to_datetime(g_["date"]))["bsr"]
        s_ = s_.reindex(pd.date_range(s_.index.min(), s_.index.max(), freq="D")).ffill(limit=14)
        f_ = s_.dropna().rename("bsr").reset_index().rename(columns={"index": "date"})
        f_["brand"], f_["asin"] = b, a_
        filled.append(f_)
    day = pd.concat(filled, ignore_index=True)
    day["date"] = day["date"].dt.strftime("%Y-%m-%d")
    day["month"] = day["date"].str[:7]
    exp_, u1000 = sales_params(domain)
    day["units"] = (SALES_REF / day["bsr"]) ** exp_
    am = (day.groupby(["brand", "asin", "month"], as_index=False)
          .agg(rank_median=("bsr", "median"), units=("units", "mean"), days=("date", "nunique")))

    # 순위 공유 찾기: 아마존은 용량·색상 묶음(한 상품 페이지)에 순위 하나를 쓴다.
    # 기록 시각이 달라 '같은 날 같은 값' 으로는 못 잡는다 (코스알엑스 2023-11~2024-04 가
    # 두 번 더해져 판매량이 2배로 부풀었다). 그래서 한 달 안에서 두 상품의 일별 순위가
    # 겹치는 날의 80% 이상에서 10% 이내로 붙어 다니면 같은 상품으로 보고 하나만 센다.
    am["dup"] = False
    piv_all = day.pivot_table(index=["brand", "month", "date"], columns="asin", values="bsr")
    for (b, mo), blk in piv_all.groupby(level=[0, 1]):
        blk = blk.dropna(axis=1, how="all")
        cols = list(blk.columns)
        if len(cols) < 2:
            continue
        # 기록이 많은 상품을 대표로 남긴다
        cols.sort(key=lambda c: -blk[c].notna().sum())
        kept = []
        for c in cols:
            same = False
            for k in kept:
                both = blk[[c, k]].dropna()
                if len(both) >= 5:
                    # 10% 이내 또는 1.5계단 이내 — 최상위권은 1위·2위만 달라도 2배라
                    # 비율만 보면 같은 상품을 못 잡는다 (코스알엑스 2023-12: 2/2, 3/3, 1/1.5 …)
                    lo_, hi_ = both.min(axis=1), both.max(axis=1)
                    close = (hi_ - lo_) <= np.maximum(1.5, 0.10 * lo_)
                    if close.mean() >= 0.75:
                        same = True
                        break
            if same:
                am.loc[(am["brand"] == b) & (am["month"] == mo) & (am["asin"] == c), "dup"] = True
            else:
                kept.append(c)
    am["units_counted"] = np.where(am["dup"], 0.0, am["units"])
    # 추정 월 판매 개수 = 지수 × '1,000위 상품의 월 판매 개수'. 아마존 표시가 '○개 이상' 하한이라
    # 이 숫자도 하한이다. 실제 표시와 비교하면 절반 정도가 2배 안에 들어온다 (bsr_calib.json).
    am["est_units"] = (am["units"] * u1000).round()
    am.to_csv(asin_monthly, index=False, encoding="utf-8")

    g = am.groupby(["brand", "month"])
    m = pd.DataFrame({
        "bsr_median": g["rank_median"].median().round(),
        "best_rank": g["rank_median"].min().round(),
        "sales_idx": g["units_counted"].sum().round(3),
        "n_asin": g["asin"].nunique(),
        "n_listing": g["dup"].apply(lambda s: int((~s).sum())),
    }).reset_index()
    m["str_median"] = (-np.log10(m["bsr_median"].clip(lower=1))).round(4)
    m["str_best"] = (-np.log10(m["best_rank"].clip(lower=1))).round(4)
    m["str_sales"] = np.log10(m["sales_idx"].clip(lower=1e-6)).round(4)
    m["bsr_strength"] = m["str_median"]            # 예전 열 이름 — 호환용
    m["est_units"] = (m["sales_idx"] * u1000).round()
    m.to_csv(monthly, index=False, encoding="utf-8")
    print(f"{monthly.name}: {len(m)}행 (지표 3종) · 지수 {exp_} · 1,000위 = 월 {u1000:,.0f}개 · "
          f"{asin_monthly.name}: {len(am)}행")
    return m.to_dict("records")


def history(key, domain, only_brand=None):
    asins_csv, daily, monthly, meta_p = paths(domain)
    if not asins_csv.exists():
        print(f"{asins_csv.name} 없음 — 먼저 --discover 로 ASIN 을 찾을 것")
        return 1
    rows = list(csv.DictReader(asins_csv.open(encoding="utf-8-sig")))
    todo = [r for r in rows if not only_brand or r["brand"] == only_brand]
    out, meta = [], {}
    for i, r in enumerate(todo, 1):
        asin, b = r["asin"].strip(), r["brand"]
        if not asin:
            continue
        print(f"  [{i}/{len(todo)}] {b:18s} {asin}")
        js = _call("product", key, domain=domain, asin=asin, history=1,
                   stats=0)
        prods = js.get("products") or []
        if not prods:
            print("    상품 없음")
            continue
        p = prods[0]
        if not title_ok(b, p.get("title")):
            print(f"    ⚠ 제목에 브랜드명 없음 — 버림: {(p.get('title') or '')[:50]}")
            continue
        arr = p.get("csv") or []
        series = arr[I_SALES] if len(arr) > I_SALES else None
        if not series:
            print("    BSR 이력 없음 (아마존 판매 기록 없음)")
            continue
        # csv[3] 은 [시각(분), 값, 시각, 값, ...]. -1 은 '값 없음'.
        n = 0
        for j in range(0, len(series) - 1, 2):
            t, v = series[j], series[j + 1]
            if v is None or v < 0:
                continue
            d = dt.datetime.utcfromtimestamp(
                (t * 60000 + KEEPA_EPOCH_MS) / 1000).date()
            out.append({"brand": b, "asin": asin, "date": d.isoformat(),
                        "bsr": v})
            n += 1
        title = (p.get("title") or "")[:70]
        meta[asin] = {"brand": b, "points": n, "title": title}
        print(f"    {n:,}개 점 · {title[:46]}")
        r["title"] = r.get("title") or title
    if not out:
        print("수집된 BSR 없음")
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    with daily.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "date", "bsr"])
        w.writeheader()
        w.writerows(out)

    mrows = aggregate(domain)
    with asins_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "title"])
        w.writeheader()
        w.writerows(rows)
    meta_p.write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "domain": DOMAINS.get(domain, domain), "asins": meta,
         "months": len(mrows), "brands": sorted({r["brand"] for r in mrows}),
         "source": f"Keepa API /product domain={domain} history=1, csv[3]=SALES rank",
         "note": "bsr_strength = -log10(BSR). 클수록 잘 팔림."},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{daily.name} {len(out):,}행 · {monthly.name} {len(mrows)}행 "
          f"· {len({r['brand'] for r in mrows})}개 브랜드")
    return 0


# 가장 오래된 상품 찾기용 검색 조건. 브랜드명 검색이 엉뚱한 상품을 물어오는 브랜드는
# 제품명(title)으로 찾는다 (VT → 헤드셋, d'alba → 슬라임, manyo → 이쑤시개 — 2026-10-15).
# 리들샷은 VT 의 다른 라인과 섞지 않는다 (퍼널의 브랜드 단위 = 리들샷 라인).
OLD_QUERY = {
    1: {"reedle shot": {"title": "reedle shot"}, "d'alba": {"title": "d'alba truffle"},
        "manyo": {"title": "ma:nyo"}},
    5: {"reedle shot": {"title": "リードルショット"}, "d'alba": {"title": "ダルバ"},
        "atopalm": {"brand": ["アトパーム"]}, "manyo": {"title": "魔女工場"}},
}


def backfill_oldest(key, domain, n_new=3, scan=12, only=None):
    """브랜드별로 아마존에 가장 먼저 등록된 상품을 n_new 개 추가한다 (PM 2026-10-15).

    왜: 지금 잘 팔리는 상품만 추적하면, 예전에 팔던 상품이 빠져 브랜드 선이 늦게 시작한다
    (센텔리안24 미국 첫 기록이 2023-03 으로 나왔지만 실제로는 2016-07 선크림부터 있었다).
    '브랜드 론칭' · '아마존 첫 기록' 축에서 왼쪽(초기)이 비는 문제를 고친다.
    판매량 합계 방식에서는 옛 상품의 판매도 브랜드 판매이므로 더하는 게 맞다.
    토큰: 브랜드당 검색 약 10 + 후보 상품 scan 개."""
    asins_csv, daily, _mo, meta_p = paths(domain)
    rows = list(csv.DictReader(asins_csv.open(encoding="utf-8-sig")))
    have = {r["asin"] for r in rows}
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    minfo = meta.get("asins") or {}
    new_rows, new_pts = [], []
    for b, brand_name in BRANDS.items():
        if only and b != only:
            continue
        sel = dict(OLD_QUERY.get(domain, {}).get(b) or {"brand": [brand_name.lower()]})
        sel.update({"sort": [["trackingSince", "asc"]], "perPage": 50, "page": 0})
        try:
            js = _call("query", key, body=sel, domain=domain)
        except Exception as e:
            print(f"  {b:18s} 검색 실패: {e}")
            continue
        cand = [a for a in (js.get("asinList") or []) if a not in have][:scan]
        if not cand:
            print(f"  {b:18s} 후보 없음")
            continue
        pj = _call("product", key, domain=domain, asin=",".join(cand), history=1, stats=0)
        good = []
        for p in pj.get("products") or []:
            if not title_ok(b, p.get("title")):
                continue
            arr = p.get("csv") or []
            series = arr[I_SALES] if len(arr) > I_SALES else None
            if not series:
                continue
            pts = []
            for j in range(0, len(series) - 1, 2):
                t, v = series[j], series[j + 1]
                if v is None or v < 0:
                    continue
                dd = dt.datetime.utcfromtimestamp((t * 60000 + KEEPA_EPOCH_MS) / 1000).date()
                pts.append({"brand": b, "asin": p["asin"], "date": dd.isoformat(), "bsr": v})
            if pts:
                good.append((pts[0]["date"], p, pts))
        good.sort(key=lambda x: x[0])
        for first, p, pts in good[:n_new]:
            title = (p.get("title") or "")[:70]
            new_rows.append({"brand": b, "asin": p["asin"], "title": title})
            new_pts += pts
            minfo[p["asin"]] = {"brand": b, "points": len(pts), "title": title, "oldest_pick": True}
            have.add(p["asin"])
        firsts = ", ".join(x[0] for x in good[:n_new])
        print(f"  {b:18s} +{min(len(good), n_new)}개 (첫 기록 {firsts or '-'})")
    if not new_rows:
        print("추가할 상품 없음")
        return 0
    with asins_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "title"])
        w.writeheader()
        w.writerows(rows + new_rows)
    with daily.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "asin", "date", "bsr"])
        w.writerows(new_pts)
    meta["asins"] = minfo
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n상품 {len(new_rows)}개 · BSR {len(new_pts):,}점 추가 → 월별 다시 계산")
    aggregate(domain)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--brand")
    ap.add_argument("--domain", type=int, default=1,
                    help="1=미국(기본) 5=일본 3=영국 4=독일")
    ap.add_argument("--aggregate", action="store_true",
                    help="Keepa 호출 없이 bsr_daily 로 월별 지표만 다시 계산")
    ap.add_argument("--backfill-oldest", action="store_true",
                    help="브랜드별로 아마존에 가장 먼저 등록된 상품 3개를 추가 (초기 이력 채우기)")
    a = ap.parse_args()
    if a.aggregate:
        aggregate(a.domain)
        return 0
    if a.backfill_oldest:
        k_ = _key()
        if not k_:
            print("KEEPA_KEY 없음")
            return 1
        return backfill_oldest(k_, a.domain, only=a.brand)
    key = _key()
    if not key:
        print("KEEPA_KEY 없음 — 환경변수 또는 .streamlit/secrets.toml [keepa] key")
        print("결제 후 키만 넣으면 이 스크립트는 그대로 돌아감.")
        return 1
    if a.discover:
        discover(key, a.domain)
        return 0
    return history(key, a.domain, a.brand)


if __name__ == "__main__":
    sys.exit(main())
