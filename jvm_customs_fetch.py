# -*- coding: utf-8 -*-
"""제이브이엠(054950) 수출 트래커 — 관세청 무역통계(tradedata.go.kr)에서 직접 수집.

Usage:
    python jvm_customs_fetch.py            # 증분: 마지막 수집 이후 월만
    python jvm_customs_fetch.py --full     # 2016-01부터 전체 재수집

왜 이 코드들인가 (2026-11-11 검증):
  * HS 3920.71 (재생 셀룰로오스 필름) = ATDPS 파우치(약포지) 원단.
    미국 통관 선하증권(ImportYeti)에서 JVM 선적의 품목코드로 확인.
    전국 수출의 ~73%가 대구 달서구(JVM 본사·공장)에서 나가고, 행선지
    상위가 네덜란드(JVM Europe)·캐나다(McKesson)·미국·스페인·벨기에 등
    JVM 시장과 일치 → 소모품 수출의 사실상 단독 지표.
  * HS 8479.89 (기타 기계) = ATDPS 본체(선하증권 코드). 단, 이 코드는
    반도체·로봇 등 온갖 기계가 섞여 있어 국가별로 걸러도 '참고'에 그침.
  * 관세청 '지역별 실적'은 HS6까지만 지원, 국가 구분 없음 — 달서구 합계만.

산출물 (data/jvm/):
    customs_392071_monthly.csv   month,cnty_cd,country_kr,country_en,region,exp_usd_k,exp_ton
    customs_847989_monthly.csv   같은 구조 (JVM 시장 국가만 보관)
    customs_dalseo_monthly.csv   month,hs,exp_usd_k  (대구 달서구 합계)
    customs_meta.json
단위: 금액 US$000 (포털 '천불'), 중량 톤. 수리일 기준 확정통계 (약 5주 시차).
"""
import datetime as dt
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
DATA = Path(__file__).resolve().parent / "data" / "jvm"
START = 2016
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
      "Referer": BASE + "/cts/index.do",
      "X-Requested-With": "XMLHttpRequest"}
HS_CONS = "392071"        # 소모품(파우치 원단)
HS_MACH = "847989"        # 기계(참고)
MACH_KEEP = {"네덜란드", "캐나다", "미국", "스페인", "벨기에", "프랑스", "호주", "뉴질랜드",
             "독일", "영국", "이탈리아", "일본", "중국", "폴란드", "스위스", "스웨덴", "덴마크",
             "노르웨이", "핀란드", "아일랜드", "포르투갈", "오스트리아", "체코공화국"}
COUNTRY_EN = {"네덜란드": "Netherlands", "캐나다": "Canada", "미국": "United States",
              "스페인": "Spain", "벨기에": "Belgium", "프랑스": "France", "호주": "Australia",
              "뉴질랜드": "New Zealand", "독일": "Germany", "영국": "United Kingdom",
              "이탈리아": "Italy", "일본": "Japan", "중국": "China", "싱가포르": "Singapore",
              "멕시코": "Mexico", "태국": "Thailand", "대만": "Taiwan", "사우디아라비아": "Saudi Arabia",
              "폴란드": "Poland", "스위스": "Switzerland", "스웨덴": "Sweden", "덴마크": "Denmark",
              "노르웨이": "Norway", "핀란드": "Finland", "아일랜드": "Ireland", "포르투갈": "Portugal",
              "오스트리아": "Austria", "체코공화국": "Czechia", "홍콩": "Hong Kong",
              "아랍에미리트 연합": "UAE", "베트남": "Vietnam", "인도": "India", "브라질": "Brazil",
              "남아프리카공화국": "South Africa", "인도네시아": "Indonesia", "말레이시아": "Malaysia",
              "필리핀": "Philippines", "이스라엘": "Israel", "튀르키예": "Turkey", "러시아 연방": "Russia"}
REGION = {"네덜란드": "Europe", "스페인": "Europe", "벨기에": "Europe", "프랑스": "Europe",
          "독일": "Europe", "영국": "Europe", "이탈리아": "Europe", "폴란드": "Europe",
          "스위스": "Europe", "스웨덴": "Europe", "덴마크": "Europe", "노르웨이": "Europe",
          "핀란드": "Europe", "아일랜드": "Europe", "포르투갈": "Europe", "오스트리아": "Europe",
          "체코공화국": "Europe", "캐나다": "North America", "미국": "North America",
          "멕시코": "Latin America", "브라질": "Latin America", "호주": "Oceania", "뉴질랜드": "Oceania"}


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "-", "None") else 0.0


def session():
    s = requests.Session()
    s.headers.update(UA)
    s.get(BASE + "/cts/index.do", timeout=30)
    for page in ("openETS0100019Q", "openETS0100027Q"):   # 국가별 / 지역별 화면 등록(필수)
        s.post(f"{BASE}/cts/hmpg/{page}.do", data={"menuId": "ETS_MNK_10200000"}, timeout=30)
    return s


def fetch_national(s, hs, fr, to):
    """월×국가 (HS6 하나). fr/to='YYYYMM' — 같은 해 안에서만."""
    payload = {"tradeKind": "ETS_MNK_1020000E", "priodKind": "MON", "priodFr": fr, "priodTo": to,
               "statsBase": "acptDd", "ttwgTpcd": "1000", "showPagingLine": "100000",
               "sortColumn": "", "sortOrder": "", "cntyNm": "",
               "hsSgnGrpCol": "HS6_SGN", "hsSgnWhrCol": "HS6_SGN", "hsSgn": hs}
    r = s.post(BASE + "/cts/hmpg/retrieveTrade.do", data=payload, timeout=90)
    r.raise_for_status()
    rows = []
    for it in r.json().get("items", []):
        period = str(it.get("priodTitle", "")).strip()
        if "." not in period:
            continue
        rows.append({"month": period.replace(".", "-"), "cnty_cd": str(it.get("cntyCd", "")).strip(),
                     "country_kr": str(it.get("cntyNm", "")).strip(),
                     "exp_usd_k": _num(it.get("expUsdAmt")), "exp_ton": _num(it.get("expTtwg"))})
    return rows


def fetch_dalseo(s, hs, fr, to):
    """대구 달서구(704) 월별 합계 (HS6)."""
    payload = {"tradeKind": "ETS_MNK_1040000A", "sidosggKind": "sgg", "priodKind": "MON",
               "priodFr": fr, "priodTo": to, "statsBase": "acptDd", "sidoCd": "27", "sggCd": "704",
               "imexTpcd": "EXP_TMPR_CD", "selectPaging": "1", "showPagingLine": "100000",
               "sortColumn": "", "sortOrder": "", "hsSgnGrpCol": "HS6_SGN", "hsSgnWhrCol": "HS6_SGN",
               "hsSgn": hs, "subHsSgn": "N"}
    r = s.post(BASE + "/cts/hmpg/retrieveTradeRegion.do", data=payload, timeout=90)
    r.raise_for_status()
    rows = []
    for it in r.json().get("items", []):
        period = str(it.get("priodTitle", "")).strip()
        if "." not in period:
            continue
        rows.append({"month": period.replace(".", "-"), "hs": hs, "exp_usd_k": _num(it.get("expUsdAmt"))})
    return rows


def latest_available(s):
    today = dt.date.today()
    y, m = today.year, today.month
    for _ in range(8):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        rows = fetch_national(s, HS_CONS, f"{y}{m:02d}", f"{y}{m:02d}")
        if rows and sum(r["exp_usd_k"] for r in rows) > 0:
            return y, m
        time.sleep(2)
    raise SystemExit("최신 공표월을 찾지 못했습니다")


def _retry(fn, label):
    for attempt in range(3):
        try:
            return fn()
        except Exception as e:
            print(f"  {label}: {type(e).__name__} 재시도 {attempt + 1}/3")
            time.sleep(15)
    raise SystemExit(f"{label} 수집 실패 — 중단(부분 저장 안 함)")


def main():
    full = "--full" in sys.argv
    DATA.mkdir(parents=True, exist_ok=True)
    p_cons, p_mach, p_dal = (DATA / "customs_392071_monthly.csv", DATA / "customs_847989_monthly.csv",
                             DATA / "customs_dalseo_monthly.csv")
    s = session()
    old = {}
    if p_cons.exists() and not full:
        old = {"cons": pd.read_csv(p_cons), "mach": pd.read_csv(p_mach), "dal": pd.read_csv(p_dal)}
        last = old["cons"]["month"].max()
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
    cons, mach, dal = [], [], []
    y = y0
    while y <= ly:
        fr = f"{y}{m0:02d}" if y == y0 else f"{y}01"
        to = f"{y}{lm:02d}" if y == ly else f"{y}12"
        cons += _retry(lambda: fetch_national(s, HS_CONS, fr, to), f"{y} 392071")
        time.sleep(1.5)
        mach += [r for r in _retry(lambda: fetch_national(s, HS_MACH, fr, to), f"{y} 847989")
                 if r["country_kr"] in MACH_KEEP]
        time.sleep(1.5)
        dal += _retry(lambda: fetch_dalseo(s, HS_CONS, fr, to), f"{y} 달서구 392071")
        time.sleep(1.5)
        dal += _retry(lambda: fetch_dalseo(s, HS_MACH, fr, to), f"{y} 달서구 847989")
        print(f"  {fr}~{to}: 392071 {len(cons)}행 누적, 847989 {len(mach)}행, 달서구 {len(dal)}행")
        y += 1
        time.sleep(2)

    def finish(new, key, path, subset):
        df = pd.DataFrame(new)
        if old:
            df = pd.concat([old[key], df])
        if "country_kr" in df.columns:
            df["country_en"] = df["country_kr"].map(COUNTRY_EN).fillna(df["country_kr"])
            df["region"] = df["country_kr"].map(REGION).fillna("Others")
        df = df.drop_duplicates(subset=subset, keep="last").sort_values(subset)
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"{path.name}: {len(df)}행, {df['month'].min()} ~ {df['month'].max()}")
        return df

    dc = finish(cons, "cons", p_cons, ["month", "cnty_cd"])
    finish(mach, "mach", p_mach, ["month", "cnty_cd"])
    finish(dal, "dal", p_dal, ["month", "hs"])
    yr = dc.assign(year=dc["month"].str[:4]).groupby("year")["exp_usd_k"].sum() / 1000
    print("392071 연간 합계 (US$mn):", {k: round(v, 1) for k, v in yr.items()})
    (DATA / "customs_meta.json").write_text(json.dumps(
        {"fetched": dt.datetime.now().isoformat(timespec="seconds"),
         "latest_month": f"{ly}-{lm:02d}",
         "source": "관세청 수출입무역통계 tradedata.go.kr — 품목별·국가별(retrieveTrade.do) + "
                   "지역별 실적(retrieveTradeRegion.do, 대구 달서구), 수리일 기준, US$000",
         "hs": {"392071": "재생 셀룰로오스 필름 = ATDPS 파우치 원단 (소모품)",
                "847989": "기타 기계 = ATDPS 본체 (타 품목 혼입, 참고용)"}},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
