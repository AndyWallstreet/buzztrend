# -*- coding: utf-8 -*-
"""K뷰티 브랜드 검색 모멘텀 스크리너 데이터 만들기.

Usage:  python brand_screener_update.py
입력:   data/cosmetics/absvol_monthly.csv   (cosmetics_absvol_update.py 산출, DataForSEO 구글애즈 월 검색수)
산출:   data/cosmetics/brand_screener.csv   브랜드 × 국가별 모멘텀 지표
        data/cosmetics/brand_screener_meta.json

지표 (모두 '월 검색수' 기준 — 구글 애즈 절대량)
  now           최근월 검색수
  m1 / m3 / m12 1·3·12개월 전 대비 증감률  (3개월 이동평균으로 비교 — 구글 값이 계단식이라 노이즈가 큼)
  peak / peak_m 자기 최고치와 그 달
  vs_peak       최근 ÷ 최고치   (1.0 = 지금이 최고, 0.3 = 전성기의 30%)
  since_peak    최고치 이후 지난 개월 수
  stage         수명주기 단계 — 아래 규칙
  score         순위용 종합점수 (3M·12M 모멘텀 + 피크 대비)

stage 규칙 (피크 대비와 12개월 모멘텀으로만 판정 — 단순하게)
  급성장   vs_peak ≥ 0.9  &  m12 ≥ +30%
  성장     m12 ≥ +10%
  정체     −10% ≤ m12 < +10%
  둔화     m12 < −10%  &  vs_peak ≥ 0.5
  쇠퇴     vs_peak < 0.5
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
GEO_KR = {"US": "미국", "JP": "일본", "GB": "영국", "AU": "호주", "CA": "캐나다", "DE": "독일", "FR": "프랑스",
          "NL": "네덜란드", "MX": "멕시코", "BR": "브라질", "SG": "싱가포르", "PH": "필리핀", "MY": "말레이시아",
          "ID": "인도네시아", "VN": "베트남", "IN": "인도", "WW": "전세계"}


def momentum(s: pd.Series, n: int) -> float:
    """n개월 전 대비 증감률 — 양쪽 다 3개월 평균으로 비교(계단식 값의 노이즈 완화)."""
    if len(s) < n + 3:
        return np.nan
    cur = s.iloc[-3:].mean()
    old = s.iloc[-(n + 3):-n].mean()
    return cur / old - 1 if old > 0 else np.nan


def stage_of(vs_peak, m12):
    if pd.isna(m12):
        return "데이터 부족"
    if vs_peak < 0.5:
        return "쇠퇴"
    if m12 >= 0.30 and vs_peak >= 0.9:
        return "급성장"
    if m12 >= 0.10:
        return "성장"
    if m12 >= -0.10:
        return "정체"
    return "둔화"


def main():
    d = pd.read_csv(DATA / "absvol_monthly.csv")
    d = d.groupby(["geo", "brand", "month"], as_index=False)["searches"].sum()   # 키워드 여러 개 → 합산
    rows = []
    for (geo, brand), g in d.groupby(["geo", "brand"]):
        g = g.sort_values("month")
        s = g.set_index("month")["searches"].astype(float)
        if s.sum() <= 0 or len(s) < 6:
            continue
        # 마지막 달이 부분집계인 경우가 있어, 전체 최신월보다 뒤쳐진 브랜드는 그대로 둠
        peak = s.max()
        peak_m = s.idxmax()
        now = s.iloc[-1]
        m12 = momentum(s, 12)
        vs_peak = now / peak if peak > 0 else np.nan
        since = (pd.Period(s.index[-1]) - pd.Period(peak_m)).n
        rows.append({
            "geo": geo, "geo_kr": GEO_KR.get(geo, geo), "brand": brand,
            "last_month": s.index[-1], "now": now,
            "m1": momentum(s, 1), "m3": momentum(s, 3), "m12": m12,
            "peak": peak, "peak_month": peak_m, "vs_peak": vs_peak, "since_peak": since,
            "months": len(s), "stage": stage_of(vs_peak, m12)})
    t = pd.DataFrame(rows)
    # 종합점수: 3M 모멘텀 30% + 12M 모멘텀 50% + 피크대비 20% (각 지표는 국가 안에서 순위 백분위로)
    def pct(x):
        return x.rank(pct=True)
    t["score"] = (t.groupby("geo")["m3"].transform(pct).fillna(0.5) * 0.3
                  + t.groupby("geo")["m12"].transform(pct).fillna(0.5) * 0.5
                  + t.groupby("geo")["vs_peak"].transform(pct).fillna(0.5) * 0.2) * 100
    t["rank"] = t.groupby("geo")["score"].rank(ascending=False, method="min").astype(int)
    t = t.sort_values(["geo", "rank"])
    t.to_csv(DATA / "brand_screener.csv", index=False, encoding="utf-8-sig")
    (DATA / "brand_screener_meta.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%d"),
        "last_month": str(t["last_month"].max()),
        "n_brands": int(t["brand"].nunique()), "n_geos": int(t["geo"].nunique()),
        "source": "DataForSEO · Google Ads 월 검색수 (cosmetics_absvol_update.py)",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"brand_screener.csv: {len(t)}행 · {t['brand'].nunique()}개 브랜드 × {t['geo'].nunique()}개국 "
          f"· 최신 {t['last_month'].max()}")
    us = t[t["geo"] == "US"][["rank", "brand", "now", "m3", "m12", "vs_peak", "stage"]]
    print(us.head(10).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))


if __name__ == "__main__":
    main()
