# -*- coding: utf-8 -*-
"""일본 K-뷰티 랭킹 추적 — @cosme 주간 TOP100 + Qoo10 Japan 뷰티 베스트셀러 TOP200.

왜 (PM 2026-10-22): 일본은 구글 검색 점유율이 낮아(야후재팬·빙) 검색량만으로는 부족.
    일본 K-뷰티 최대 채널 Qoo10 과 입소문 1위 @cosme 의 공개 랭킹에서 한국 브랜드가
    몇 개·몇 위에 있는지를 매일/매주 쌓아 "일본시장 K-beauty 따로 보기" 에 쓴다.

출처·방식
  @cosme  https://www.cosme.net/ranking/products/ (+ page/1..9, week/2, week/3) — 매주 금요일 갱신, 집계기간 표시.
          robots.txt 는 /ranking 허용. 요청 간 2초.
  Qoo10   https://m.qoo10.jp/gmkt.inc/Mobile/Bestsellers/Default.aspx?group_code=2 (ビューティ TOP200, 모바일 페이지 —
          PC 페이지는 클라우드플레어가 막음). robots.txt Crawl-delay 2 준수. 히스토리는 없어서 오늘부터 하루 1장씩.
  한국 브랜드 판정: data/cosmetics/jp_kbrands.csv 의 aliases (영문/가타카나) 가 브랜드명(@cosme) 또는
          셀러 브랜드명·상품명(Qoo10) 에 들어 있으면 해당 key 로 표시.

출력 (data/cosmetics/)
  jp_cosme_rank.csv  period_start, period_end, rank, brand, brand_id, product, product_id, category, rating, votes,
                     price, onsale, status, kbrand, fetched
  jp_qoo10_rank.csv  date, rank, delta, brand, title, price, rating, reviews, gd, kbrand, fetched
Usage: python jp_kbeauty_update.py [--weeks 3]   (같은 주/같은 날은 덮어씀)
"""
import html
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cosmetics"
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/120.0 Safari/537.36")
UA_MO = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/120.0 Mobile Safari/537.36")
DELAY = 2.0


def load_kbrands():
    k = pd.read_csv(DATA / "jp_kbrands.csv", encoding="utf-8-sig")
    rules = []
    for _, r in k.iterrows():
        for a in str(r["aliases"]).split("|"):
            a = a.strip()
            if a:
                rules.append((a.lower(), r["key"]))
    rules.sort(key=lambda x: -len(x[0]))  # 긴 별칭 먼저 (VT 보다 VTコスメティックス)
    return rules


def match_kbrand(text, rules):
    t = (text or "").lower()
    for alias, key in rules:
        if len(alias) <= 2:   # 'VT' 같은 짧은 별칭은 단어 경계로
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", t):
                return key
        elif alias in t:
            return key
    return ""


def _g(block, pat):
    m = re.search(pat, block, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


# ---------------------------------------------------------------- @cosme
def cosme_week(week, rules, sess):
    """week=1 이번 주, 2 지난주, 3 지지난주 → (period_start, period_end, rows)."""
    rows, period = [], None
    for pg in range(0, 10):
        base = "https://www.cosme.net/ranking/products/"
        if week > 1:
            base += f"week/{week}/"
        url = base + (f"page/{pg}" if pg else "")
        r = sess.get(url, headers={"User-Agent": UA_PC, "Accept-Language": "ja,en;q=0.8"}, timeout=30)
        r.raise_for_status()
        t = r.text
        if period is None:
            m = re.search(r"集計期間：(\d{4}/\d{1,2}/\d{1,2})〜(\d{4}/\d{1,2}/\d{1,2})", t)
            if not m:
                raise RuntimeError("@cosme 집계기간을 못 찾음: " + url)
            period = tuple(pd.Timestamp(x).date().isoformat() for x in m.groups())
        i = t.find('<div id="list-item">')
        j = t.find("cmn-modules-paging", i + 10)
        body = re.sub(r"<script.*?</script>", " ", t[i:j], flags=re.S)
        for dl in re.findall(r"<dl\b.*?</dl>", body, re.S):
            rk = re.search(r'alt="(\d+)位"', dl) or re.search(r'<span class="num">(\d+)</span>', dl)
            if not rk:
                continue
            brand = _g(dl, r'<span class="brand"><a href="https://www\.cosme\.net/brands/\d+/">([^<]+)</a>')
            rows.append({"period_start": period[0], "period_end": period[1], "rank": int(rk.group(1)),
                         "brand": brand, "brand_id": _g(dl, r'brands/(\d+)/'),
                         "product": _g(dl, r'<span class="item"><a href="https://www\.cosme\.net/products/\d+/"\s*>([^<]+)</a>'),
                         "product_id": _g(dl, r'products/(\d+)/'),
                         "category": _g(dl, r'<span class="category">\[<a[^>]*>([^<]+)</a>'),
                         "rating": _g(dl, r'<p class="rating[^"]*">([\d.]+)</p>'),
                         "votes": _g(dl, r'class="count">([\d,]+)</a>').replace(",", ""),
                         "price": _g(dl, r'<p class="price">([^<]+)</p>').replace("\xa0", " "),
                         "onsale": _g(dl, r'<p class="onsale">発売日：([^<]+)</p>'),
                         "status": _g(dl, r'ranking_icons/ico_(\w+)\.png'),
                         "kbrand": match_kbrand(brand, rules),
                         "fetched": date.today().isoformat()})
        time.sleep(DELAY)
    df = pd.DataFrame(rows).drop_duplicates("rank").sort_values("rank")
    return period, df


# ---------------------------------------------------------------- Qoo10
def qoo10_beauty(rules, sess):
    url = "https://m.qoo10.jp/gmkt.inc/Mobile/Bestsellers/Default.aspx?group_code=2"
    r = sess.get(url, headers={"User-Agent": UA_MO, "Accept-Language": "ja,en;q=0.8"}, timeout=40)
    r.raise_for_status()
    t = r.text
    if "ビューティ" not in (re.search(r"<title>(.*?)</title>", t, re.S) or [""])[0] and "ビューティ" not in t[:5000]:
        print("  Qoo10: 제목에 ビューティ 가 없음 — 카테고리 코드가 바뀌었을 수 있음")
    rows = []
    for p in t.split('ga-product="bestseller"')[1:]:
        rank = _g(p, r'class="rank_current">(\d+)<')
        if not rank:
            continue
        brand = _g(p, r'class="common_ui_seller_brand[^"]*"[^>]*>(.*?)</span>')
        title = _g(p, r'<span class="list_v2_title\s*">(.*?)</span>') or _g(p, r'<img class="thumbnail_image"[^>]*alt="([^"]*)"')
        rows.append({"date": date.today().isoformat(), "rank": int(rank),
                     "delta": _g(p, r'class="rank_delta (\w+)"'),
                     "brand": re.sub(r"<[^>]+>", "", brand), "title": title,
                     "price": _g(p, r'price_final_value"[^>]*>([\d,]+)<').replace(",", ""),
                     "rating": _g(p, r'class="rate_score">([\d.]+)<'),
                     "reviews": _g(p, r'class="rate_count">\(([\d,]+)\)').replace(",", ""),
                     "gd": _g(p, r'goodscode=(\d+)'),
                     "kbrand": match_kbrand(brand + " " + title, rules),
                     "fetched": date.today().isoformat()})
    return pd.DataFrame(rows).drop_duplicates("rank").sort_values("rank")


def upsert(path, new, keys):
    old = pd.read_csv(path, encoding="utf-8-sig") if path.exists() else pd.DataFrame()
    if len(old):
        drop = old.merge(new[keys].drop_duplicates(), on=keys, how="inner")
        old = old.merge(new[keys].drop_duplicates(), on=keys, how="left", indicator=True)
        old = old[old["_merge"] == "left_only"].drop(columns="_merge")
    df = pd.concat([old, new], ignore_index=True).sort_values(keys)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def main():
    weeks = 3 if "--weeks" not in sys.argv else int(sys.argv[sys.argv.index("--weeks") + 1])
    rules = load_kbrands()
    sess = requests.Session()
    # @cosme
    pc = DATA / "jp_cosme_rank.csv"
    have = set(pd.read_csv(pc, encoding="utf-8-sig")["period_start"]) if pc.exists() else set()
    for w in range(1, weeks + 1):
        try:
            period, df = cosme_week(w, rules, sess)
        except Exception as e:  # noqa: BLE001
            print(f"@cosme week{w} 실패: {e}")
            continue
        if period[0] in have and w > 1:
            print(f"@cosme {period[0]}~{period[1]}: 이미 있음 (건너뜀)")
            continue
        upsert(pc, df, ["period_start", "rank"])
        k = df[df["kbrand"] != ""]
        print(f"@cosme {period[0]}~{period[1]}: {len(df)}개 중 한국 브랜드 {len(k)}개 "
              f"({', '.join(k['kbrand'].unique()[:8])})")
    # Qoo10
    try:
        q = qoo10_beauty(rules, sess)
        upsert(DATA / "jp_qoo10_rank.csv", q, ["date", "rank"])
        k = q[q["kbrand"] != ""]
        print(f"Qoo10 ビューティ {date.today()}: {len(q)}개 중 한국 브랜드 {len(k)}개 "
              f"(TOP50 안 {int((k['rank'] <= 50).sum())}개) — {', '.join(k['kbrand'].unique()[:10])}")
    except Exception as e:  # noqa: BLE001
        print(f"Qoo10 실패: {e}")


if __name__ == "__main__":
    main()
