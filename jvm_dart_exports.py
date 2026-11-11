# -*- coding: utf-8 -*-
"""제이브이엠 DART 매출실적(수출) → data/jvm/dart_exports_*.csv

입력: ~/dart-jvm/records.json (dart-jvm 파이프라인이 만든 DART 표 레코드)
출력:
  dart_exports_annual.csv     year, machine, consumable, goods, total, rcept_no   (KRWmn, 사업보고서)
  dart_exports_quarterly.csv  quarter, machine, consumable, goods, total, basis   (KRWmn, 누적→분기 차감)
basis: 'Q' = 분기보고서 단독값, 'cum-diff' = 반기/사업보고서 누적에서 앞 분기 차감(작성자 계산)
"""
import json
from pathlib import Path

import pandas as pd

REC = Path.home() / "dart-jvm" / "records.json"
OUT = Path(__file__).resolve().parent / "data" / "jvm"
OUT.mkdir(parents=True, exist_ok=True)

RCEPT = {"2025.12": "20260323001116", "2026.03": "20260515001024", "2026.06": "20260814003335"}
KEYS = {"machine": "조제시스템 / 수 출", "consumable": "주요소모품 외 / 수 출",
        "goods": "기타상품 / 수 출", "total": "합 계 / 수 출"}


def main():
    rec = json.load(open(REC, encoding="utf-8"))
    rows = {}
    for x in rec:
        if "매출실적" not in x.get("table", "") or x.get("period", "") < "2016":
            continue
        lab = x.get("label", "")
        for k, suffix in KEYS.items():
            if lab.endswith(suffix) and x.get("money_mn") is not None:
                key = (x["period"], x["kind"])
                d = rows.setdefault(key, {"rcept_no": RCEPT.get(x["period"], "")})
                d[k] = float(x["money_mn"])          # 같은 표가 두 번 잡히면 같은 값
    ann = []
    for (p, kind), d in sorted(rows.items()):
        if kind == "사업" and p.endswith(".12"):
            ann.append({"year": int(p[:4]), **{k: round(d.get(k, float("nan")), 1) for k in KEYS},
                        "rcept_no": d["rcept_no"]})
    pd.DataFrame(ann).to_csv(OUT / "dart_exports_annual.csv", index=False, encoding="utf-8")

    # 누적 → 분기: 1Q(분기) 단독, 2Q = 반기-1Q, 3Q = 3Q분기(누적 9M)-반기, 4Q = 사업-9M
    cum = {}
    for (p, kind), d in rows.items():
        y, m = int(p[:4]), int(p[5:7])
        if m not in (3, 6, 9, 12):
            continue
        cum[(y, m)] = d
    q = []
    for (y, m), d in sorted(cum.items()):
        prev = cum.get((y, m - 3)) if m > 3 else None
        basis = "Q" if m == 3 else "cum-diff"
        if m > 3 and prev is None:
            continue
        row = {"quarter": f"{y}Q{m // 3}", "basis": basis, "rcept_no": d["rcept_no"]}
        for k in KEYS:
            v = d.get(k)
            if v is None:
                continue
            row[k] = round(v - (prev.get(k, 0.0) if prev else 0.0), 1)
        q.append(row)
    pd.DataFrame(q).to_csv(OUT / "dart_exports_quarterly.csv", index=False, encoding="utf-8")
    print(pd.DataFrame(ann).tail(3).to_string())
    print(pd.DataFrame(q).tail(6).to_string())


if __name__ == "__main__":
    main()
