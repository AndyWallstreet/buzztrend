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
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
SD = ROOT / "data" / "cosmetics_sd"

# BSR 브랜드 지표 (keepa_bsr_history.aggregate 가 만든 열). python funnel_study.py --bsr best
#   sales  ① 추정 판매량 합계 (기본) — 신상품이 선을 끌어내리지 않음
#   best   ② 주력 상품 순위 — 그 달 가장 잘 팔린 상품
#   median 예전 방식 (상품 중앙값) — 비교용
BSR_COL = {"sales": "str_sales", "best": "str_best", "median": "str_median"}
METHOD = "sales"
if "--bsr" in sys.argv:
    METHOD = sys.argv[sys.argv.index("--bsr") + 1]
    assert METHOD in BSR_COL, f"--bsr 는 {list(BSR_COL)} 중 하나"
SFX = "" if METHOD == "sales" else f"_{METHOD}"   # 산출 파일 이름 끝

# 검색 브랜드 → 매출 주체. single=True 면 그 회사 매출의 대부분이 이 브랜드임.
MAP = {
    "madeca cream":     ("동국제약",       "dongkook_brand", False),
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
    # 전세계 = 16개국 합. 미국만 보면 지역이 안 맞는 브랜드가 왜곡된다 —
    # 리들샷은 검색의 90%가 일본인데 매출은 연결 전사라, US 만 쓰면 상관이
    # 음수로 나왔다(PM 2026-10-15). 'WW' 행은 2025-10 부터뿐이고 16개국과
    # 중복이라 뺀다.
    a = a[(a["geo"] != "WW") & (a["searches"] < 1_000_000)]   # tirtir 이상치 제거
    # 나라·키워드마다 최신월이 달라서, 가장 짧은 쪽에 맞춰 잘라야 마지막 달이
    # '일부만 더한 값'으로 푹 꺼지지 않는다.
    cut = a.groupby(["geo", "keyword"])["month"].max().min()
    a = a[a["month"] <= cut]
    a_geo = a.copy()                      # 나라별 원본 — BSR 가중치에 쓴다
    a = a.groupby(["brand", "month"], as_index=False)["searches"].sum()
    a["q"] = a["month"].map(q_of)
    ab = a.groupby(["brand", "q"], as_index=False)["searches"].mean().rename(columns={"searches": "abs_search"})

    # BSR: 미국(amazon.com) + 일본(amazon.co.jp). 순위는 마켓플레이스 안에서만
    # 의미가 있어 그냥 평균내면 안 된다. 그 브랜드가 각 나라에서 실제로 얼마나
    # 검색되는지(= 시장 크기 대리)로 가중평균한다 — 리들샷은 검색의 90%가
    # 일본이라 일본 BSR 이 거의 전부를 결정해야 맞다.
    b = None
    bits = []
    for fn, geo in (("bsr_monthly.csv", "US"), ("bsr_monthly_jp.csv", "JP")):
        fp = DATA / fn
        if fp.exists():
            x = (pd.read_csv(fp)[["brand", "month", BSR_COL[METHOD]]]
                 .rename(columns={BSR_COL[METHOD]: "bsr_strength"}).copy())
            x["geo"] = geo
            bits.append(x)
    if bits:
        bs = pd.concat(bits, ignore_index=True)
        wt = (a_geo[a_geo["geo"].isin(["US", "JP"])]
              .groupby(["brand", "month", "geo"], as_index=False)["searches"].sum()
              .rename(columns={"searches": "w"}))
        bs = bs.merge(wt, on=["brand", "month", "geo"], how="left")
        # 검색 데이터가 없는 달은 그 나라를 똑같이 취급 (가중치 1)
        bs["w"] = bs["w"].fillna(1.0)
        bs["wx"] = bs["w"] * bs["bsr_strength"]
        g2 = bs.groupby(["brand", "month"], as_index=False)[["wx", "w"]].sum()
        g2["bsr_strength"] = g2["wx"] / g2["w"]
        g2["q"] = g2["month"].map(q_of)
        b = (g2.groupby(["brand", "q"], as_index=False)["bsr_strength"]
               .mean().rename(columns={"bsr_strength": "bsr"}))

    g = pd.read_csv(DATA / "gtrends_life_US.csv")
    g["q"] = g["date"].astype(str).str[:7].map(q_of)
    gt = g.groupby(["brand", "q"], as_index=False)["value"].mean().rename(columns={"value": "rel_search"})
    out = ab.merge(gt, on=["brand", "q"], how="outer")
    if b is not None:
        out = out.merge(b, on=["brand", "q"], how="outer")
    return out


def revenue_panel():
    rows = []
    # brand_revenue_q / _unlisted 는 억원 단위로 저장돼 있다 (ODM 트래커와 공용).
    # 퍼널 안에서는 KRWmn 으로 통일한다 — 상관 계산엔 영향 없지만 표기가 섞이면 안 된다.
    q = pd.read_csv(SD / "brand_revenue_q.csv")
    q["rev_eok"] = q["rev_eok"] * 100
    for b, (co, src, _s) in MAP.items():
        if src == "listed":
            g = q[q["co"] == co][["q", "rev_eok"]].copy().sort_values("q")
            if len(g):
                g["rev_yoy"] = g["rev_eok"] / g["rev_eok"].shift(4) - 1   # 분기는 4분기 전과 비교
                g["brand"] = b
                rows.append(g.rename(columns={"rev_eok": "rev"}))
    # 동국제약: 센텔리안24 단독 매출은 DART에 없다. 가장 가까운 공시 라인이
    # '제품-기타(화장품 포함)' — 센텔리안24가 이 라인의 대부분이다.
    # 연간 합이 v5d 워크북의 제품-기타(내수+수출)와 일치함을 확인했다
    # (2024 265,638 / 2025 275,528 백만원). 단위는 억원으로 변환.
    # 실제 센텔리안24 브랜드 매출 (v5d Data!r65, 언론·증권 추정). 2019~2021 미공표라 구멍이 있다.
    # 분기는 공시가 없다 — 분기 추세가 필요하면 dongkook_prod_other_q.csv(제품-기타 프록시)를 쓸 것.
    fb = SD / "dongkook_centellian_y.csv"
    if fb.exists():
        for b, (co, src, _s) in MAP.items():
            if src == "dongkook_brand":
                g = pd.read_csv(fb).dropna(subset=["rev_krwmn"]).sort_values("year").copy()
                g["rev_eok"] = g["rev_krwmn"]          # 패널 단위 = KRWmn
                g["rev_yoy"] = [g["rev_eok"].iloc[i] / g["rev_eok"].iloc[i - 1] - 1
                                if i and g["year"].iloc[i] - g["year"].iloc[i - 1] == 1 else float("nan")
                                for i in range(len(g))]            # 연도가 안 이어지면 YoY 계산 안 함
                g["brand"] = b
                g["q"] = g["year"].astype(int).astype(str) + "Q4"
                rows.append(g[["q", "rev_eok", "rev_yoy", "brand"]].rename(columns={"rev_eok": "rev"}))

    f = SD / "dongkook_prod_other_q.csv"
    if f.exists() and False:   # 프록시는 기본 비활성 — 실제 브랜드 매출을 쓴다
        for b, (co, src, _s) in MAP.items():
            if src == "dongkook_seg":
                g = pd.read_csv(f).sort_values("q").copy()
                g["rev_yoy"] = g["rev_eok"] / g["rev_eok"].shift(4) - 1   # 분기 → 4분기 전
                g["brand"] = b
                rows.append(g[["q", "rev_eok", "rev_yoy", "brand"]].rename(columns={"rev_eok": "rev"}))

    u = pd.read_csv(SD / "brand_revenue_unlisted.csv")
    u["rev_eok"] = u["rev_eok"] * 100
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


def yoy(df, col, per=4, log=False):
    """전년 대비 변화. log=True 면 나눗셈이 아니라 뺄셈을 쓴다.

    왜: bsr_strength = -log10(BSR) 은 음수다. 음수끼리 나누면 개선됐는데도
    부호가 뒤집힌다 (-2 / -3 - 1 = -0.33). 이미 로그값이므로 차이가 곧
    변화율이다. 2026-10-15 에 이것 때문에 BSR 상관이 전부 음수로 나왔다."""
    out = []
    for b, g in df.sort_values("q").groupby("brand"):
        g = g.copy()
        g[col + "_yoy"] = (g[col] - g[col].shift(per) if log
                           else g[col] / g[col].shift(per) - 1)
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
    if "bsr" in p.columns:
        p = yoy(p, "bsr", log=True)      # 이미 로그값 — 뺄셈
    p = p.sort_values(["brand", "q"])
    p.to_csv(DATA / f"funnel_panel{SFX}.csv", index=False, encoding="utf-8-sig")

    # ---- 단계별 상관 (시차 0~3분기)
    res = []
    links = [("rel_search_yoy", "abs_search_yoy", "① 상대검색 → 절대검색"),
             ("abs_search_yoy", "rev_yoy", "② 절대검색 → 매출"),
             ("rel_search_yoy", "rev_yoy", "③ 상대검색 → 매출 (전체 건너뛰기)")]
    if "bsr_yoy" in p.columns:                  # BSR 이 들어오면 칸을 쪼갠다
        links += [("abs_search_yoy", "bsr_yoy", "②a 절대검색 → BSR"),
                  ("bsr_yoy", "rev_yoy", "②b BSR → 매출")]
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
    out.to_csv(DATA / f"funnel_result{SFX}.csv", index=False, encoding="utf-8-sig")

    # ---- 브랜드별 상관 (PM 우선순위). BSR 칸은 Keepa 결제 후 채운다.
    bres = []
    for b, g in p.groupby("brand"):
        g = g.sort_values("q").reset_index(drop=True)
        rq = g.dropna(subset=["rev"])["q"]
        row = {"brand": b, "회사": MAP[b][0], "단일브랜드": MAP[b][2],
               "매출주기": "분기" if rq.str.endswith(("Q1", "Q2", "Q3")).any() else "연간",
               "매출관측수": int(len(rq))}
        pairs = [("rel_search_yoy", "abs_search_yoy", "①상대→절대"),
                 ("abs_search_yoy", "rev_yoy", "②절대→매출"),
                 ("rel_search_yoy", "rev_yoy", "③상대→매출")]
        if "bsr_yoy" in p.columns:
            pairs += [("abs_search_yoy", "bsr_yoy", "②a절대→BSR"),
                      ("bsr_yoy", "rev_yoy", "②bBSR→매출")]
        for xc, yc, tag in pairs:
            # 실제 겹치는 점 개수(nmax)는 R이 안 나와도 보고한다 — n=0 으로 보이면
            # '데이터 없음'으로 오해하게 된다(PM 2026-10-15).
            best, nmax = (None, None, 0, None), 0
            for lag in range(0, 4):
                y = g[yc].shift(-lag) if lag else g[yc]
                r_, p_, n_ = corr_p(g[xc], y, "spearman")
                nmax = max(nmax, n_)
                if pd.notna(r_) and (best[0] is None or abs(r_) > abs(best[0])):
                    best = (r_, p_, n_, lag)
            if best[0] is None:
                best = (None, None, nmax, None)
            row[tag + "_R"], row[tag + "_p"], row[tag + "_n"], row[tag + "_시차"] = best
        bres.append(row)
    bb = pd.DataFrame(bres).sort_values("②절대→매출_R", ascending=False)
    bb.to_csv(DATA / f"funnel_by_brand{SFX}.csv", index=False, encoding="utf-8-sig")

    (DATA / f"funnel_meta{SFX}.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%d"),
        "n_brands": int(p["brand"].nunique()),
        "quarters": [str(p["q"].min()), str(p["q"].max())],
        "note": "YoY 기준. 전세계(16개국 합) 절대검색·미국 상대검색. 매출은 회사 단위(멀티브랜드는 희석). BSR 축은 Keepa 결제 후 추가 예정.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"패널: {p['brand'].nunique()}개 브랜드 · {p['q'].nunique()}개 분기")
    print(f"매출 있는 브랜드: {p.dropna(subset=['rev'])['brand'].nunique()}개")
    pd.set_option("display.width", 160)
    print(out.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))


if __name__ == "__main__":
    main()
