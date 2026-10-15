# -*- coding: utf-8 -*-
"""BSR → 판매량 환산식 점검 — 아마존 '지난달 X개 이상 구매' 표시로 직접 맞춘다.

Usage:
    python keepa_sales_calib.py            # 미국·일본 추적 상품 전체 (ASIN 당 1토큰)
    python keepa_sales_calib.py --no-fetch # 이미 받은 파일로 다시 계산만

왜 (PM 2026-10-15): 판매량 지수 = (1000/순위)^0.85 의 0.85 는 학계 책 연구에서 빌려온
    가정이었다. Keepa 는 아마존 상품 페이지의 '지난달 X개 이상 구매' 값(monthlySold)을
    기록한다. 이 실제 판매 표시와 같은 달의 순위를 비교해 뷰티 카테고리의 지수를 직접 구한다.
    같은 호출로 Keepa 의 브랜드 칸(brand)도 받아, 상품명 대신 브랜드 칸으로 오매칭을 검사한다.

주의:
  · monthlySold 는 구간 하한값이다 (50+, 100+, … 1K+, 10K+ …). 실제는 그보다 많다.
    그래서 '개수' 는 과소추정이고, 지수(기울기)는 구간 때문에 조금 흐려질 수 있다.
  · 표시는 2023년 하반기부터만 있다.

산출 (data/cosmetics/):
    bsr_calib_points{sfx}.csv   asin·월별 순위 중앙값 vs 판매 표시 중앙값
    bsr_calib.json              시장별 기울기(지수)·절편·R²·1,000위 월 판매량
    bsr_brandcheck{sfx}.csv     ASIN 별 Keepa 브랜드 칸
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import keepa_bsr_history as K

DATA = K.DATA
MK = {1: "US", 5: "JP"}
# Keepa 브랜드 칸이 이 중 하나를 포함하면 정상 (대소문자·띄어쓰기 무시)
BRAND_OK = {
    "madeca cream": ["centellian", "dongkook", "센텔리안", "동국", "センテリアン"],
    "reedle shot": ["vt"], "atopalm": ["atopalm", "neopharm", "アトパーム"],
    "medicube": ["medicube", "メディキューブ", "apr"], "d'alba": ["d'alba", "dalba", "ダルバ"],
    "manyo": ["manyo", "ma:nyo", "魔女"], "laneige": ["laneige", "ラネージュ", "amorepacific"],
    "anua": ["anua", "アヌア"], "cosrx": ["cosrx"], "skin1004": ["skin1004"],
    "beauty of joseon": ["joseon", "朝鮮"], "tirtir": ["tirtir"], "torriden": ["torriden", "トリデン"],
    "numbuzin": ["numbuzin", "ナンバーズイン"], "round lab": ["round", "ラウンドラボ"],
    "abib": ["abib", "アビブ"], "mixsoon": ["mixsoon", "ミクスン"], "biodance": ["biodance", "バイオダンス"],
}


def norm(s):
    return (s or "").lower().replace(" ", "")


def brand_ok(b, brand_field):
    bf = norm(brand_field)
    return bool(bf) and any(norm(w) in bf for w in BRAND_OK.get(b, []))


def conv(m):
    return pd.Timestamp("2011-01-01") + pd.Timedelta(minutes=int(m))


def fetch(domain, key):
    asins_csv = K.paths(domain)[0]
    sfx = "" if domain == 1 else "_jp"
    rows = pd.read_csv(asins_csv, encoding="utf-8-sig")
    out_sold, out_brand = [], []
    al = list(rows["asin"])
    for i in range(0, len(al), 20):              # 한 번에 20개씩 (ASIN 당 1토큰)
        chunk = al[i:i + 20]
        js = K._call("product", key, domain=domain, asin=",".join(chunk), history=1, stats=0)
        for p in js.get("products") or []:
            b = rows.loc[rows["asin"] == p["asin"], "brand"].iloc[0]
            out_brand.append({"brand": b, "asin": p["asin"], "keepa_brand": p.get("brand") or "",
                              "title": (p.get("title") or "")[:80],
                              "brand_ok": brand_ok(b, p.get("brand"))})
            h = p.get("monthlySoldHistory") or []
            for j in range(0, len(h) - 1, 2):
                if h[j + 1] is not None and h[j + 1] > 0:
                    out_sold.append({"asin": p["asin"], "date": conv(h[j]).strftime("%Y-%m-%d"),
                                     "sold": h[j + 1]})
        print(f"  {MK[domain]} {min(i + 20, len(al))}/{len(al)} · 남은 토큰 {js.get('tokensLeft')}")
    pd.DataFrame(out_brand).to_csv(DATA / f"bsr_brandcheck{sfx}.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(out_sold).to_csv(DATA / f"bsr_monthly_sold{sfx}.csv", index=False, encoding="utf-8")


def fit(domain):
    sfx = "" if domain == 1 else "_jp"
    s = pd.read_csv(DATA / f"bsr_monthly_sold{sfx}.csv")
    s["month"] = s["date"].str[:7]
    sm = s.groupby(["asin", "month"], as_index=False)["sold"].median()
    am = pd.read_csv(DATA / f"bsr_asin_monthly{sfx}.csv")
    bc = pd.read_csv(DATA / f"bsr_brandcheck{sfx}.csv", encoding="utf-8-sig")
    okset = set(bc.loc[bc["brand_ok"], "asin"])
    x = sm.merge(am[["brand", "asin", "month", "rank_median", "days", "dup"]], on=["asin", "month"])
    x = x[x["asin"].isin(okset) & (x["days"] >= 20) & (x["rank_median"] > 0)]   # 한 달 대부분 기록 있는 달만
    # 순위를 공유한 브랜드-월은 뺀다: 순위는 묶음(페이지) 하나인데 판매 표시는 상품마다 따로라
    # 같은 순위에 작은 판매가 붙어 기울기가 낮아진다 (미국 0.52 → 뺀 뒤 0.66, 2026-10-15 확인).
    shared = x.groupby(["brand", "month"])["dup"].transform("any")
    x = x[~shared]
    x.to_csv(DATA / f"bsr_calib_points{sfx}.csv", index=False, encoding="utf-8")
    lx, ly = np.log10(x["rank_median"]), np.log10(x["sold"])
    b, a = np.polyfit(lx, ly, 1)                  # (참고용) 직선 하나: log10(판매) = a + b·log10(순위)
    pred_lin = a + b * lx
    # 두 구간 공식 (B, PM 2026-10-15): KNOT 위에서 꺾인다.
    #   3,000위 안쪽은 순위 차이가 판매 차이로 거의 안 이어지고(기울기 ~0.2),
    #   바깥은 가파르다(~1.1). 직선 하나(A)는 2배 안 47% → 두 구간 79%.
    #   log10(판매) = a + b_top·log10(순위) + b_add·max(log10(순위) − log10(KNOT), 0)
    X = _design(lx)
    coef = np.linalg.lstsq(X, ly, rcond=None)[0]
    if coef[1] > 0:          # 안쪽 기울기가 양수 = 순위가 나빠질수록 더 판다는 뜻 → 말이 안 되므로 평평(0)하게 고정
        c2 = np.linalg.lstsq(X[:, [0, 2]], ly, rcond=None)[0]
        coef = np.array([c2[0], 0.0, c2[1]])
    pred = X @ coef
    r2 = 1 - ((ly - pred) ** 2).sum() / ((ly - ly.mean()) ** 2).sum()
    # C: 브랜드 하나를 빼고 맞춘 뒤 그 브랜드에 적용 — 처음 보는 브랜드에도 맞는지
    lbo = pd.Series(index=x.index, dtype=float)
    for bnd in x["brand"].unique():
        tr = (x["brand"] != bnd).values
        c_ = np.linalg.lstsq(X[tr], ly.values[tr], rcond=None)[0]
        if c_[1] > 0:
            cc = np.linalg.lstsq(X[tr][:, [0, 2]], ly.values[tr], rcond=None)[0]
            c_ = np.array([cc[0], 0.0, cc[1]])
        lbo[~tr] = X[~tr] @ c_
    lbo_ratio = 10 ** np.abs(ly - lbo.values)
    # 부트스트랩 95% 구간 (상품 단위로 다시 뽑기 — 같은 상품의 달끼리는 서로 닮아서)
    rng = np.random.default_rng(0)
    asins = x["asin"].unique()
    bs = []
    for _ in range(500):
        pick = rng.choice(asins, len(asins), replace=True)
        xx = pd.concat([x[x["asin"] == q] for q in pick])
        bb, _aa = np.polyfit(np.log10(xx["rank_median"]), np.log10(xx["sold"]), 1)
        bs.append(-bb)
    # 같은 상품 안에서만 본 기울기 (상품마다 다른 '크기' 를 빼고 순위 변화 ↔ 판매 변화만)
    xw = x.copy()
    xw["lx"] = lx - xw.groupby("asin")["rank_median"].transform(lambda v: np.log10(v).mean())
    xw["ly"] = ly - xw.groupby("asin")["sold"].transform(lambda v: np.log10(v).mean())
    xw = xw[xw.groupby("asin")["asin"].transform("size") >= 6]
    bw = -np.polyfit(xw["lx"], xw["ly"], 1)[0] if len(xw) > 20 else float("nan")
    # 오차: 예측 ÷ 실제 (로그 차이). 몇 배 안에 몇 % 가 들어오나
    ratio = 10 ** np.abs(ly - pred)
    ratio_lin = 10 ** np.abs(ly - pred_lin)
    sold_at = lambda r: round(float(10 ** (_design([np.log10(r)]) @ coef)[0]))
    return {
        "model": "piecewise", "knot_rank": KNOT,
        "a": round(float(coef[0]), 4), "b_top": round(float(coef[1]), 4), "b_add": round(float(coef[2]), 4),
        "slope_top": round(float(-coef[1]), 3), "slope_tail": round(float(-(coef[1] + coef[2])), 3),
        "within_2x": round(float((ratio <= 2).mean()), 3),
        "within_3x": round(float((ratio <= 3).mean()), 3),
        "median_err_x": round(float(np.median(ratio)), 2),
        "lbo_within_2x": round(float((lbo_ratio <= 2).mean()), 3),     # C: 브랜드 빼고 검증
        "lbo_median_err_x": round(float(np.median(lbo_ratio)), 2),
        "linear_within_2x": round(float((ratio_lin <= 2).mean()), 3),  # A: 참고
        "linear_median_err_x": round(float(np.median(ratio_lin)), 2),
        "market": MK[domain], "n_points": int(len(x)), "n_asin": int(x["asin"].nunique()),
        "exponent_linear": round(-b, 3), "ci95_linear": [round(float(np.percentile(bs, 2.5)), 3),
                                                         round(float(np.percentile(bs, 97.5)), 3)],
        "exponent_within_asin": round(float(bw), 3), "r2": round(float(r2), 3),
        "sold_at_rank_1000": sold_at(1000), "sold_at_rank_100": sold_at(100), "sold_at_rank_10": sold_at(10),
        "months": [x["month"].min(), x["month"].max()],
        "brand_mismatch_dropped": int((~bc["brand_ok"]).sum()),
    }


KNOT = 3000


def _design(lx):
    """두 구간 공식의 설명변수: [1, log10(순위), max(log10(순위) − log10(KNOT), 0)]."""
    lx = np.asarray(lx, dtype=float)
    return np.c_[np.ones(len(lx)), lx, np.maximum(lx - np.log10(KNOT), 0.0)]


def main():
    if "--no-fetch" not in sys.argv:
        key = K._key()
        for dom in (1, 5):
            fetch(dom, key)
    res = {}
    for dom in (1, 5):
        res[MK[dom]] = fit(dom)
        print(json.dumps(res[MK[dom]], ensure_ascii=False))
    (DATA / "bsr_calib.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
