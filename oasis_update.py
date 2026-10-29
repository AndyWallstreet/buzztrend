# -*- coding: utf-8 -*-
"""오아시스 × 토스 신선식품 트래커 — 토스쇼핑 전용관(2026-09-17) 이후 오아시스가 잘 되는지 추적.

왜 (PM 2026-10-29): 토스 시너지는 실적(4Q26, 2027-02 공시)보다 먼저 보여야 함. 공개 데이터 4개를 매주 쌓아
    "리뷰가 늘고 있나 · 검색이 늘고 있나 · 앱 순위가 오르나 · 뉴스가 나오나" 를 한 장에 본다.
    경쟁사(컬리·쿠팡·SSG·이마트몰·네이버 / 배민·쿠팡이츠·요기요)도 같은 지표로 나란히.

지표 (data/oasis/)
  reviews.csv   오아시스몰 베스트 상품 리뷰 수 — https://www.oasis.co.kr/product/best 의 info_reviewNumber.
                주간 증가분 = 주문량 대리지표 (토스 주문도 결국 여기로 쌓임). 컬리·쿠팡은 막혀 있어 오아시스만.
  trends.csv    구글 트렌드 KR 주간 검색량 (gtrends.py 직접 호출). 그룹 A 장보기, 그룹 B 음식배달. 5개 제한 → 2회 호출.
  apprank.csv   앱스토어 KR '쇼핑' 무료 TOP200 순위 (itunes.apple.com RSS genre=6024) + 음식배달은 '음식 및 음료' genre=6023.
  news.csv      구글뉴스 RSS "오아시스마켓 토스" 등 주간 기사 수·제목.
Usage: python oasis_update.py            (같은 날은 덮어씀. 매주 월요일 작업 스케줄러)
"""
import datetime as dt
import html
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "oasis"
DATA.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
import gtrends  # noqa: E402

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
      "Accept-Language": "ko-KR,ko;q=0.9"}
TODAY = dt.date.today().isoformat()

# 경쟁사 — 이름 매칭 키워드 (앱 이름·뉴스에 쓰임)
GROCERY = {"오아시스": ["오아시스마켓", "오아시스 마켓"], "컬리": ["컬리", "마켓컬리"],
           "쿠팡": ["쿠팡(Coupang)"], "SSG": ["SSG.COM", "쓱닷컴"], "이마트몰": ["이마트몰"],
           "네이버": ["네이버플러스 스토어"]}   # 토스쇼핑은 토스 앱(금융) 안이라 쇼핑 순위에 안 잡힘
FOOD = {"배민": ["배달의민족"], "쿠팡이츠": ["쿠팡이츠"], "요기요": ["요기요"]}


def _upsert(name, df, keys):
    p = DATA / name
    if p.exists():
        old = pd.read_csv(p, encoding="utf-8-sig")
        # 키를 전부 문자열로 맞춰 비교 (CSV 에서 읽은 product_id 는 int, 새 값은 str 이라 안 맞던 버그)
        okey = old[keys].astype(str).apply(tuple, axis=1)
        nkey = set(df[keys].astype(str).apply(tuple, axis=1))
        old = old[~okey.isin(nkey)]
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return df


# ---------------------------------------------------------------- 1. 오아시스 리뷰 수
def reviews():
    """베스트 페이지 상품 50개 → 각 상품의 /product/{id}/commentList (XHR) 에서 '전체 (N건)' 을 읽음.
    베스트 목록 HTML 에는 리뷰 수가 없고, 상세 페이지도 XHR 로 채우기 때문. 상품당 1초 쉼."""
    r = requests.get("https://www.oasis.co.kr/product/best", headers=UA, timeout=30)
    r.raise_for_status()
    t = r.text
    ids, names, prices = [], {}, {}
    # 상품명은 <div class="infoTit"><a href="/product/detail/{id}">이름</a>, 가격은 바로 뒤 <em>4,290</em>원
    for m in re.finditer(r'class="infoTit">\s*<a href="/product/detail/(\d+)[^"]*">(.*?)</a>(.{0,400}?)<em>([\d,]+)</em>',
                         t, re.S):
        pid = m.group(1)
        if pid in names:
            continue
        names[pid] = html.unescape(re.sub(r"\s+", " ", m.group(2))).strip()[:60]
        prices[pid] = int(m.group(4).replace(",", ""))
        ids.append(pid)
    ids = ids[:60]
    rows = []
    xh = {**UA, "X-Requested-With": "XMLHttpRequest"}
    for i, pid in enumerate(ids, 1):
        try:
            c = requests.get(f"https://www.oasis.co.kr/product/{pid}/commentList",
                             params={"page": 1, "premiumYn": "N"}, headers=xh, timeout=30).text
            mm = re.search(r"전체 \(([\d,]+)건\)", c)
            if not mm:
                continue
            rows.append({"date": TODAY, "rank": i, "product_id": pid, "name": names.get(pid, ""),
                         "price": prices.get(pid), "reviews": int(mm.group(1).replace(",", ""))})
        except Exception as e:
            print(f"  상품 {pid}: {type(e).__name__}")
        time.sleep(1.0)
    d = pd.DataFrame(rows).drop_duplicates(subset=["date", "product_id"])
    if not len(d):
        raise RuntimeError("리뷰 수 파싱 0건 — 마크업 바뀐 듯. /product/best 확인")
    _upsert("reviews.csv", d, ["date", "product_id"])
    print(f"리뷰: 베스트 {len(d)}개 상품, 리뷰 합계 {d['reviews'].sum():,}")
    return d


# ---------------------------------------------------------------- 2. 구글 트렌드 KR
def trends():
    out = []
    for grp, kws in (("장보기", ["오아시스마켓", "컬리", "쿠팡 로켓프레시", "토스쇼핑", "SSG"]),
                     ("음식배달", ["배달의민족", "쿠팡이츠", "요기요", "오아시스마켓"])):
        df = gtrends.fetch_trends(kws, geo="KR", timeframe="today 12-m")
        df["group"] = grp
        out.append(df)
        time.sleep(3)
    d = pd.concat(out, ignore_index=True)
    d["fetched"] = TODAY
    d.to_csv(DATA / "trends.csv", index=False, encoding="utf-8-sig")   # 12개월 전체를 매번 교체
    last = d[d.date == d.date.max()]
    print("트렌드 최신주:", dict(zip(last.keyword, last.value)))
    return d


# ---------------------------------------------------------------- 3. 앱스토어 순위
def apprank():
    rows = []
    for genre, label in ((6024, "쇼핑"), (6023, "음식및음료")):
        u = f"https://itunes.apple.com/kr/rss/topfreeapplications/limit=200/genre={genre}/json"
        j = requests.get(u, headers=UA, timeout=30).json()
        names = [e["im:name"]["label"] for e in j["feed"]["entry"]]
        for i, n in enumerate(names, 1):
            for co, keys in {**GROCERY, **FOOD}.items():
                if any(k in n for k in keys):
                    rows.append({"date": TODAY, "genre": label, "company": co, "rank": i, "app": n[:40]})
        time.sleep(1)
    d = pd.DataFrame(rows).drop_duplicates(subset=["date", "genre", "company"])
    _upsert("apprank.csv", d, ["date", "genre", "company"])
    print("앱순위:", {f"{r.company}({r.genre[:2]})": r.rank for r in d.itertuples()})
    return d


# ---------------------------------------------------------------- 4. 구글뉴스
def news():
    from email.utils import parsedate_to_datetime
    rows = []
    for q in ('"오아시스마켓"', '오아시스 토스쇼핑', '"컬리" 새벽배송', '"토스쇼핑"'):
        r = requests.get("https://news.google.com/rss/search",
                         params={"q": f"{q} when:7d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                         headers=UA, timeout=30)
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            continue
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            src = (it.findtext("source") or "").strip()
            if src and title.endswith(" - " + src):
                title = title[: -(len(src) + 3)]
            try:
                d0 = parsedate_to_datetime(it.findtext("pubDate")).astimezone().strftime("%Y-%m-%d")
            except Exception:
                d0 = ""
            rows.append({"week": TODAY, "query": q, "date": d0, "title": title, "press": src,
                         "url": (it.findtext("link") or "").strip()})
        time.sleep(0.5)
    d = pd.DataFrame(rows).drop_duplicates(subset=["query", "title"])
    _upsert("news.csv", d, ["week", "query", "title"])
    print("뉴스(7일):", d.groupby("query").size().to_dict())
    return d


if __name__ == "__main__":
    for fn in (reviews, trends, apprank, news):
        try:
            fn()
        except Exception as e:
            print(f"  ✗ {fn.__name__}: {type(e).__name__}: {str(e)[:120]}")
    print("완료", TODAY)
