# -*- coding: utf-8 -*-
"""커버리지 트래커 — DART 공시 + 네이버 뉴스 수집.

Usage:
    python coverage_update.py              # 최근 30일 공시 + 뉴스
    python coverage_update.py --days 90
    (then: git add data/coverage && git commit && git push)

입력:  data/coverage/coverage.csv   (name,ticker,corp_code,... 수기 관리)
산출:  data/coverage/filings.csv    ticker,name,rcept_dt,report_nm,rcept_no,url,flag
       data/coverage/news.csv       ticker,name,date,title,press,url
       data/coverage/prices.csv     ticker,name,close,chg_1d,chg_1w,chg_1m,date
       data/coverage/meta.json

주의: Streamlit Cloud(해외 IP)는 DART 접속이 막혀 있음 → 반드시 로컬에서 돌려 CSV 를 커밋할 것.
"""
import datetime as dt
import json
import re
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

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "coverage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}

# 중요 공시 = 휴가 중에도 봐야 하는 것 (제목에 이 단어가 있으면 ★)
IMPORTANT = [
    ("실적", r"영업\(잠정\)|매출액또는손익구조|결산실적|분기보고서|반기보고서|사업보고서"),
    ("자본", r"유상증자|무상증자|전환사채|신주인수권|교환사채|자기주식"),
    ("지분", r"주식등의대량보유|임원ㆍ주요주주|최대주주"),
    ("M&A·투자", r"타법인주식|영업양수|합병|분할|신규시설투자"),
    ("공급계약", r"공급계약|수주"),
    ("배당", r"현금ㆍ현물배당|배당"),
    ("경고", r"소송|횡령|배임|감사보고서|관리종목|상장폐지|불성실"),
]


def dart_key():
    m = re.search(r'API_KEY = "(\w+)"', (Path.home() / "dart-kolmar" / "step1_corpcode.py").read_text(encoding="utf-8")) \
        if (Path.home() / "dart-kolmar" / "step1_corpcode.py").exists() else None
    if m:
        return m.group(1)
    for p in sorted((Path.home() / "dart-kolmar").glob("step1*.py")):
        m = re.search(r'API_KEY = "(\w+)"', p.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    raise RuntimeError("DART API key 를 못 찾음")


def flag_of(title: str) -> str:
    for tag, pat in IMPORTANT:
        if re.search(pat, title.replace(" ", "")):
            return tag
    return ""


def filings(cov, key, days):
    end = dt.date.today()
    beg = end - dt.timedelta(days=days)
    rows = []
    for x in cov.itertuples():
        page = 1
        while True:
            try:
                j = requests.get("https://opendart.fss.or.kr/api/list.json",
                                 params={"crtfc_key": key, "corp_code": f"{int(x.corp_code):08d}",
                                         "bgn_de": beg.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                                         "page_no": page, "page_count": 100}, timeout=40).json()
            except Exception as e:
                print(f"  {x.name}: {type(e).__name__}")
                break
            if j.get("status") != "000":
                break
            for it in j.get("list", []):
                rows.append({"ticker": f"{int(x.ticker):06d}", "name": x.name,
                             "rcept_dt": f"{it['rcept_dt'][:4]}-{it['rcept_dt'][4:6]}-{it['rcept_dt'][6:]}",
                             "report_nm": it["report_nm"].strip(), "flt_nm": it.get("flr_nm", ""),
                             "rcept_no": it["rcept_no"],
                             "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it['rcept_no']}",
                             "flag": flag_of(it["report_nm"])})
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
            time.sleep(0.12)
        time.sleep(0.12)
    d = pd.DataFrame(rows)
    if len(d):
        d = d.sort_values(["rcept_dt", "name"], ascending=[False, True])
        d.to_csv(DATA / "filings.csv", index=False, encoding="utf-8-sig")
    print(f"공시 {len(d):,}건 ({beg}~{end}), 중요 {int((d['flag'] != '').sum()) if len(d) else 0}건")
    return d


def news(cov, per=15, days=14):
    """구글 뉴스 RSS — 종목명으로 최근 기사 (한국어). 네이버 검색은 마크업이 자주 바뀌어 안 씀."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    rows = []
    for x in cov.itertuples():
        q = f'"{x.name}" when:{days}d'
        try:
            r = requests.get("https://news.google.com/rss/search",
                             params={"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                             headers=UA, timeout=30)
            root = ET.fromstring(r.text)
        except Exception as e:
            print(f"  {x.name}: {type(e).__name__}")
            continue
        for it in root.findall(".//item")[:per]:
            title = (it.findtext("title") or "").strip()
            src = (it.findtext("source") or "").strip()
            if src and title.endswith(" - " + src):
                title = title[: -(len(src) + 3)]
            try:
                d0 = parsedate_to_datetime(it.findtext("pubDate")).astimezone().strftime("%Y-%m-%d %H:%M")
            except Exception:
                d0 = ""
            rows.append({"ticker": f"{int(x.ticker):06d}", "name": x.name, "date": d0,
                         "title": title, "press": src, "url": (it.findtext("link") or "").strip()})
        time.sleep(0.5)
    d = pd.DataFrame(rows)
    if len(d):
        d = d.drop_duplicates(subset=["name", "title"]).sort_values("date", ascending=False)
        d["collected"] = dt.date.today().isoformat()
        d.to_csv(DATA / "news.csv", index=False, encoding="utf-8-sig")
    print(f"뉴스 {len(d):,}건 · {d['name'].nunique() if len(d) else 0}개 종목")
    return d


def prices(cov):
    """네이버 일별 종가 — 1일·1주·1개월 등락률."""
    rows = []
    for x in cov.itertuples():
        code = f"{int(x.ticker):06d}"
        try:
            r = requests.get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=40&requestType=0",
                             headers=UA, timeout=30)
            items = re.findall(r'<item data="([^"]+)"', r.text)
        except Exception:
            continue
        if not items:
            continue
        px = [(v.split("|")[0], float(v.split("|")[4])) for v in items if v.split("|")[4].replace(".", "").isdigit()]
        if not px:
            continue
        d0, c0 = px[-1]
        get = lambda n: px[-1 - n][1] if len(px) > n else None
        rows.append({"ticker": code, "name": x.name, "date": f"{d0[:4]}-{d0[4:6]}-{d0[6:]}", "close": c0,
                     "chg_1d": c0 / get(1) - 1 if get(1) else None,
                     "chg_1w": c0 / get(5) - 1 if get(5) else None,
                     "chg_1m": c0 / get(20) - 1 if get(20) else None})
        time.sleep(0.25)
    d = pd.DataFrame(rows)
    if len(d):
        d.to_csv(DATA / "prices.csv", index=False, encoding="utf-8-sig")
    print(f"주가 {len(d)}개 종목")
    return d


def main():
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 30
    cov = pd.read_csv(DATA / "coverage.csv")
    key = dart_key()
    f = filings(cov, key, days)
    n = news(cov)
    p = prices(cov)
    (DATA / "meta.json").write_text(json.dumps({
        "as_of": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "days": days, "n_stocks": int(len(cov)),
        "n_filings": int(len(f)), "n_news": int(len(n)), "n_prices": int(len(p)),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("완료 — git add data/coverage && git commit && git push")


if __name__ == "__main__":
    main()
