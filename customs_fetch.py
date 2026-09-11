# -*- coding: utf-8 -*-
"""관세청 수출입무역통계(tradedata.go.kr)에서 화장품 수출 직접 수집.

Usage:
    python customs_fetch.py                # 증분: 마지막 수집 이후 월만
    python customs_fetch.py --full         # 2016-01부터 전체 재수집

엔드포인트: POST /cts/hmpg/retrieveTrade.do (공개 통계조회 화면이 쓰는 JSON API,
공공누리 제1유형 — 출처 표시 후 자유 이용). 월×국가×HS4, 수리일 기준.

산출물 (data/cosmetics/):
    customs_monthly.csv.gz  month,country_kr,cnty_cd,region,country_en,hs,exp_usd_k,exp_ton
    customs_exports.csv     연간 집계 (기존 페이지 호환: year,region,country_en,country_kr,hs,usd_k)
    customs_meta.json       수집 시각·최신 월

- 값 단위: 금액 US$000 (portal 표기 "천불"), 중량 톤
- 최신 월 = 확정통계 공표분 (7월 확정은 9월 초 공표 — 약 5주 시차)
- region/영문 국가명은 기존 정리본 매핑 재사용, 미매핑은 'Others'/한글명 유지
"""
import datetime as dt
import gzip
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

BASE = "https://tradedata.go.kr"
DATA = Path(__file__).resolve().parent / "data" / "cosmetics"
HS = ["3303", "3304", "3305", "3306", "3307"]
HS_LABEL = {"3303": "3303 Perfume", "3304": "3304 Skincare/Makeup",
            "3305": "3305 Haircare", "3306": "3306 Oral care",
            "3307": "3307 Shaving/Deo·Other"}
START = 2016
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
      "Referer": BASE + "/cts/index.do",
      "X-Requested-With": "XMLHttpRequest"}


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "-", "None") else 0.0


def fetch_months(s, fr, to):
    """fr/to = 'YYYYMM' — 월×국가×HS4 rows."""
    payload = {
        "tradeKind": "ETS_MNK_1020000E",      # 품목별+국가별
        "priodKind": "MON", "priodFr": fr, "priodTo": to,
        "statsBase": "acptDd", "ttwgTpcd": "1000",
        "showPagingLine": "100000",            # 페이징 없이 전체 반환
        "sortColumn": "", "sortOrder": "",
        "cntyNm": "", "hsSgnGrpCol": "HS4_SGN", "hsSgnWhrCol": "HS4_SGN",
        "hsSgn": ",".join(HS),
    }
    r = s.post(BASE + "/cts/hmpg/retrieveTrade.do", data=payload, timeout=60)
    r.raise_for_status()
    js = r.json()
    rows = []
    for it in js.get("items", []):
        period = str(it.get("priodTitle", "")).strip()
        if "." not in period:                  # '총계' 등 집계행 제외
            continue
        hs = str(it.get("hsSgn", "")).strip()
        if hs not in HS:
            continue
        rows.append({
            "month": period.replace(".", "-"),
            "country_kr": str(it.get("cntyNm", "")).strip(),
            "cnty_cd": str(it.get("cntyCd", "")).strip(),
            "hs": HS_LABEL[hs],
            "exp_usd_k": _num(it.get("expUsdAmt")),
            "exp_ton": _num(it.get("expTtwg")),
        })
    return rows


def month_iter(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def latest_available(s):
    """조회화면 월 셀렉트의 최신값을 대신해, 최근 6개월을 역순으로 찔러 확인."""
    today = dt.date.today()
    y, m = today.year, today.month
    for _ in range(8):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        rows = fetch_months(s, f"{y}{m:02d}", f"{y}{m:02d}")
        if rows and sum(r["exp_usd_k"] for r in rows) > 0:
            return y, m
        time.sleep(2)
    raise SystemExit("최신 공표월을 찾지 못했습니다")


def main():
    full = "--full" in sys.argv
    DATA.mkdir(parents=True, exist_ok=True)
    out_m = DATA / "customs_monthly.csv.gz"

    s = requests.Session()
    s.headers.update(UA)
    s.get(BASE + "/cts/index.do", timeout=30)          # 세션 쿠키
    s.post(BASE + "/cts/hmpg/openETS0100019Q.do",      # 조회화면 등록(필수)
           data={"menuId": "ETS_MNK_10200000"}, timeout=30)

    old = None
    if out_m.exists() and not full:
        old = pd.read_csv(out_m)
        last = old["month"].max()
        y0, m0 = int(last[:4]), int(last[5:7]) + 1
        if m0 > 12:
            y0, m0 = y0 + 1, 1
    else:
        y0, m0 = START, 1

    ly, lm = latest_available(s)
    print(f"최신 공표월: {ly}.{lm:02d} | 수집 시작: {y0}.{m0:02d}")
    if (y0, m0) > (ly, lm):
        print("이미 최신: 수집할 새 월 없음")
        return

    # 연 단위 청크로 요청 (한 번에 12개월)
    all_rows = []
    y = y0
    while y <= ly:
        fr = f"{y}{m0:02d}" if y == y0 else f"{y}01"
        to = f"{y}{lm:02d}" if y == ly else f"{y}12"
        for attempt in range(3):
            try:
                rows = fetch_months(s, fr, to)
                break
            except Exception as e:
                print(f"  {y}: {type(e).__name__} 재시도 {attempt + 1}/3")
                time.sleep(20)
        else:
            raise SystemExit(f"{y}년 수집 실패 — 중단(부분 저장 안 함)")
        print(f"  {fr}~{to}: {len(rows)}행")
        all_rows += rows
        y += 1
        time.sleep(3)

    new = pd.DataFrame(all_rows)
    df = (pd.concat([old, new]) if old is not None else new)
    df = df.drop_duplicates(subset=["month", "cnty_cd", "hs"], keep="last")

    # region/영문명 매핑 (기존 정리본에서)
    ref_p = DATA / "customs_exports.csv"
    if ref_p.exists():
        ref = pd.read_csv(ref_p)[["country_kr", "country_en", "region"]] \
            .drop_duplicates("country_kr")
        mp_en = dict(zip(ref["country_kr"], ref["country_en"]))
        mp_rg = dict(zip(ref["country_kr"], ref["region"]))
    else:
        mp_en, mp_rg = {}, {}
    df["country_en"] = df["country_kr"].map(mp_en).fillna(df["country_kr"])
    df["region"] = df["country_kr"].map(mp_rg).fillna("Others")

    df = df.sort_values(["month", "country_kr", "hs"])
    with gzip.open(out_m, "wt", encoding="utf-8", newline="") as f:
        df.to_csv(f, index=False)
    print(f"customs_monthly.csv.gz: {len(df)}행, "
          f"{df['month'].min()} ~ {df['month'].max()}")

    # 연간 집계 → 기존 페이지 파일 교체 (이제 출처가 관세청 직접)
    df["year"] = df["month"].str[:4].astype(int)
    ann = df.groupby(["year", "region", "country_en", "country_kr", "hs"],
                     as_index=False)["exp_usd_k"].sum()
    ann = ann.rename(columns={"exp_usd_k": "usd_k"})
    ann.to_csv(ref_p, index=False, encoding="utf-8")
    yr = ann.groupby("year")["usd_k"].sum() / 1e6
    print("연간 합계 (US$bn):",
          {int(k): round(v, 2) for k, v in yr.items()})

    (DATA / "customs_meta.json").write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "latest_month": f"{ly}-{lm:02d}", "source": "tradedata.go.kr "
         "retrieveTrade.do (월×국가×HS4, 수리일 기준, US$000)"},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
