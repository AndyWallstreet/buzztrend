# -*- coding: utf-8 -*-
"""K뷰티 수요 퍼널 검증 — 상대검색 → 절대검색 → (BSR) → 매출.

Usage:  python funnel_study.py
산출 (data/cosmetics/):
    funnel_panel.csv     브랜드 × 분기 패널 (검색 2종 + 매출)
    funnel_result.csv    단계별 상관·시차·유의성
    funnel_meta.json

왜: "검색이 뛰면 몇 분기 뒤에 매출이 따라오나"를 브랜드 전체로 검증해 표본을 키운다.
    한 종목(동국제약)만 보면 n이 너무 작아 우연과 구분이 안 된다.

방법:
  · 수준(level)이 아니라 YoY 증감률로 본다 — 둘 다 우상향이면 가짜 상관이 나오기 때문.
  · 검색은 월별 → 분기 평균. 매출은 분기(상장)·연간(비상장).
  · 시차 0/1/2분기를 각각 돌려 어느 시차에서 가장 세게 붙는지 본다.
  · 브랜드를 쌓은 패널 회귀가 아니라 '브랜드 내 상관'을 먼저 보고, 전체는 pooled 로 본다.
한계: 회사 매출 ≠ 브랜드 매출(아모레=라네즈 등 멀티브랜드는 희석). single_brand 열로 구분함.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
SD = ROOT / "data" / "cosmetics_sd"

# 검색 브랜드 → 매출 주체. single=True 면 그 회사 매출의 대부분이 이 브랜드임.
MAP = {
    "madeca cream":     ("동국제약",       "dongkook_seg", False),
    "reedle shot":      ("브이티",         "listed",       True),
    "atopalm":          ("네오팜",         "listed",       False),
    "medicube":         ("에이피알",       "listed",       True),
    "d'alba":           ("달바글로벌",     "listed",       True),
    "manyo":            ("마녀공장",       "listed",       True),
    "laneige":          ("아모레퍼시픽",   "listed",       False),
    "anua":             ("더파운더즈",     "unlisted",     True),
    "cosrx":            ("코스알엑스",     "unlisted",     True),
    "skin1004":         ("크레이버코퍼레이션", "unlisted",  True),
    "beauty of joseon": ("구다이글로벌",   "unlisted",     True),
    "tirtir":           ("티르티르",       "unlisted",     True),
    "torriden":         ("토리든",         "unlisted",     True),
    "numbuzin":         ("비나우",         "unlisted",     True),
    "round lab":        ("서린컴퍼니",     "unlisted",     True),
    "abib":             ("포컴퍼니",       "unlisted",     True),
    "mixsoon":          ("파켓",           "unlisted",     True),
    "biodance":         ("뷰티셀렉션",     "unlisted",     True),
}


def q_of(m):
    y, mm = int(str(m)[:4]), int(str(m)[5:7])
    return f"{y}Q{(mm - 1) // 3 + 1}"


def search_panel():
    """절대검색(DataForSEO)·상대검색(구글트렌드) → 브랜드 × 분기."""
    a = pd.read_csv(DATA / "absvol_monthly.csv")
    a = a[(a["geo"] == "US") & (a["searches"] < 1_000_000)]          # tirtir 이상치 제거
    a = a.groupby(["brand", "month"], as_index=False)["searches"].sum()
    a["q"] = a["month"].map(q_of)
    ab = a.groupby(["brand", "q"], as_index=False)["searches"].mean().rename(columns={"searches": "abs_search"})

    g = pd.read_csv(DATA / "gtrends_life_US.csv")
    g["q"] = g["date"].astype(str).str[:7].map(q_of)
    gt = g.groupby(["brand", "q"], as_index=False)["value"].mean().rename(columns={"value": "rel_search"})
    return ab.merge(gt, on=["brand", "q"], how="outer")


def revenue_panel():
    rows = []
    q = pd.read_csv(SD / "brand_revenue_q.csv")
    for b, (co, src, _s) in MAP.items():
        if src == "listed":
            g = q[q["co"] == co][["q", "rev_eok"]].copy().sort_values("q")
            if len(g):
                g["rev_yoy"] = g["rev_eok"] / g["rev_eok"].shift(4) - 1   # 분기는 4분기 전과 비교
                g["brand"] = b
                rows.append(g.rename(columns={"rev_eok": "rev"}))
    u = pd.read_csv(SD / "brand_revenue_unlisted.csv")
    for b, (co, src, _s) in MAP.items():
        if src == "unlisted":
            g = u[(u["company"] == co) & (u.get("type", "brand") == "brand")][["year", "rev_eok"]].copy()
            if len(g):
                g = g.sort_values("year")
                g["rev_yoy"] = g["rev_eok"] / g["rev_eok"].shift(1) - 1   # 연간은 '1년 전'과 비교 (분기 4칸 아님)
                g["brand"] = b
                g["q"] = g["year"].astype(int).astype(str) + "Q4"
                rows.append(g[["q", "rev_eok", "rev_yoy", "brand"]].rename(columns={"rev_eok": "rev"}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["brand", "q", "rev", "rev_yoy"])


def yoy(df, col, per=4):
    out = []
    for b, g in df.sort_values("q").groupby("brand"):
        g = g.copy()
        g[col + "_yoy"] = g[col] / g[col].shift(per) - 1
        out.append(g)
    return pd.concat(out)


def corr_p(x, y, method="spearman"):
    """상관과 양측 p값. 기본은 스피어만(순위) — 검색 증감률에 +3,447% 같은 극단값이
    섞여 있어 피어슨은 그 한 점에 끌려다닌다(anua 2023Q4). 순위로 보면 영향이 없다."""
    m = pd.notna(x) & pd.notna(y) & np.isfinite(x) & np.isfinite(y)
    x, y = pd.Series(np.asarray(x)[m]), pd.Series(np.asarray(y)[m])
    n = len(x)
    if n < 6 or x.std() == 0 or y.std() == 0:
        return np.nan, np.nan, n
    if method == "spearman":
        x, y = x.rank(), y.rank()
    x, y = x.values, y.values
    r = float(np.corrcoef(x, y)[0, 1])
    if abs(r) >= 1:
        return r, 0.0, n
    t = r * np.sqrt((n - 2) / (1 - r * r))
    # t 분포 양측 p — 정규근사 + 보정 (n이 작아도 과소평가 안 되게 보수적으로)
    from math import erfc, sqrt
    p = erfc(abs(t) / sqrt(2))
    return r, float(min(1.0, p)), n


def main():
    s = search_panel()
    r = revenue_panel()
    p = s.merge(r, on=["brand", "q"], how="outer")
    p = p[p["brand"].isin(MAP)].copy()
    p["회사"] = p["brand"].map(lambda b: MAP[b][0])
    p["단일브랜드"] = p["brand"].map(lambda b: MAP[b][2])
    p = yoy(yoy(p, "abs_search"), "rel_search")
    p = p.sort_values(["brand", "q"])
    p.to_csv(DATA / "funnel_panel.csv", index=False, encoding="utf-8-sig")

    # ---- 단계별 상관 (시차 0~3분기)
    res = []
    links = [("rel_search_yoy", "abs_search_yoy", "① 상대검색 → 절대검색"),
             ("abs_search_yoy", "rev_yoy", "② 절대검색 → 매출"),
             ("rel_search_yoy", "rev_yoy", "③ 상대검색 → 매출 (전체 건너뛰기)")]
    for xc, yc, name in links:
        for lag in range(0, 4):
            xs, ys = [], []
            for b, g in p.groupby("brand"):
                g = g.sort_values("q").reset_index(drop=True)
                x = g[xc].values
                y = g[yc].shift(-lag).values if lag else g[yc].values
                xs += list(x)
                ys += list(y)
            rs, ps, n = corr_p(pd.Series(xs), pd.Series(ys), "spearman")
            rp, _pp, _ = corr_p(pd.Series(xs), pd.Series(ys), "pearson")
            res.append({"단계": name, "시차(분기)": lag, "R(순위)": rs, "p값": ps, "R(피어슨)": rp, "n": n,
                        "유의": "✅" if (pd.notna(ps) and ps < 0.05) else ("△" if pd.notna(ps) and ps < 0.10 else "❌")})
    for xc, yc, name in links[1:]:
        for lag in range(0, 4):
            xs, ys = [], []
            for b_, g in p[p["단일브랜드"]].groupby("brand"):
                g = g.sort_values("q").reset_index(drop=True)
                xs += list(g[xc].values)
                ys += list(g[yc].shift(-lag).values if lag else g[yc].values)
            rs, ps, n = corr_p(pd.Series(xs), pd.Series(ys), "spearman")
            rp, _pp, _ = corr_p(pd.Series(xs), pd.Series(ys), "pearson")
            res.append({"단계": name + " [단일브랜드만]", "시차(분기)": lag, "R(순위)": rs, "p값": ps,
                        "R(피어슨)": rp, "n": n,
                        "유의": "✅" if (pd.notna(ps) and ps < 0.05) else ("△" if pd.notna(ps) and ps < 0.10 else "❌")})
    out = pd.DataFrame(res)
    out.to_csv(DATA / "funnel_result.csv", index=False, encoding="utf-8-sig")

    (DATA / "funnel_meta.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%d"),
        "n_brands": int(p["brand"].nunique()),
        "quarters": [str(p["q"].min()), str(p["q"].max())],
        "note": "YoY 기준. 미국 검색. 매출은 회사 단위(멀티브랜드는 희석). BSR 축은 Keepa 결제 후 추가 예정.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"패널: {p['brand'].nunique()}개 브랜드 · {p['q'].nunique()}개 분기")
    print(f"매출 있는 브랜드: {p.dropna(subset=['rev'])['brand'].nunique()}개")
    pd.set_option("display.width", 160)
    print(out.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))


if __name__ == "__main__":
    main()
