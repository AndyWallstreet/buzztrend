# -*- coding: utf-8 -*-
"""YG(122870) FnGuide 컨센서스 스냅샷 → data/yg/consensus_fn.csv 에 하루 1줄 추가.

왜: 워크북의 Quantiwise 일별 컨센서스(vs CONSENSUS 시트)는 PM이 엑셀에서 새로고침할 때만 늘어난다
(마지막 2026-09-07). 사이트 차트가 멈추지 않도록 FnGuide 공개 엔드포인트로 매일 한 점씩 쌓는다.
앱(yg_dashboard)은 Quantiwise 시계열 뒤에 이 파일의 더 새로운 날짜를 이어 붙인다.

엔드포인트: wcomp.fnguide.com/CompanyInfo/getCnsTrend (로그인 불필요, 억원). VAL1=현재, VAL2=1개월 전,
VAL3=3개월 전, VAL4=6개월 전, VAL5=1년 전. 첫 실행 때 1M/3M 전 값도 대략 날짜(−30/−90일)로 백필한다.
Usage: python yg_consensus_fn.py          # 오늘 1줄 추가 (같은 날 재실행 = 덮어씀)
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

DATA = Path(__file__).resolve().parent / "data" / "yg"
OUT = DATA / "consensus_fn.csv"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://wcomp.fnguide.com/"}
URL = "https://wcomp.fnguide.com/CompanyInfo/getCnsTrend?cmp_cd=122870&consol_typ=C&lang=KR&freq_typ={ft}&select_gsym={gs}"


def pull(ft, gs):
    r = requests.get(URL.format(ft=ft, gs=gs), headers=H, timeout=30)
    r.raise_for_status()
    out = {}
    for row in r.json()["dataset"]["data"]:
        if row["ACC_NM"] in ("매출액", "영업이익"):
            out[row["ACC_NM"]] = [None if v in (None, "N/A", "") else float(v) for v in
                                  (row["VAL1"], row["VAL2"], row["VAL3"], row["VAL4"], row["VAL5"])]
    return out


def main():
    a = pull("Y", "202612")
    q3 = pull("Q", "202609")
    q4 = pull("Q", "202612")
    today = date.today()
    rows = []
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    # 첫 실행: 1M/3M 전 값을 근사 날짜로 백필 (정확한 날짜가 아니라 'src' 로 표시)
    if old.empty:
        for i, days, src in ((1, 30, "fn_1m"), (2, 90, "fn_3m")):
            rows.append({"date": (today - timedelta(days=days)).isoformat(), "src": src,
                         "rev_eok": a["매출액"][i], "op_eok": a["영업이익"][i],
                         "rev3q_eok": q3["매출액"][i], "op3q_eok": q3["영업이익"][i],
                         "rev4q_eok": q4["매출액"][i], "op4q_eok": q4["영업이익"][i]})
    rows.append({"date": today.isoformat(), "src": "fn",
                 "rev_eok": a["매출액"][0], "op_eok": a["영업이익"][0],
                 "rev3q_eok": q3["매출액"][0], "op3q_eok": q3["영업이익"][0],
                 "rev4q_eok": q4["매출액"][0], "op4q_eok": q4["영업이익"][0]})
    new = pd.DataFrame(rows)
    df = pd.concat([old, new], ignore_index=True) if not old.empty else new
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    df.to_csv(OUT, index=False, encoding="utf-8")
    last = df.iloc[-1]
    print(f"consensus_fn.csv: {len(df)}일 | {last['date']} 2026E 매출 {last['rev_eok']:,.0f}억 / "
          f"영업이익 {last['op_eok']:,.0f}억 | 3Q26 {last['rev3q_eok']:,.0f} / {last['op3q_eok']:,.0f}")


if __name__ == "__main__":
    main()
