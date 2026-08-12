# -*- coding: utf-8 -*-
"""KOBIS 좌석 통계 — 실제 좌석수·좌석판매율을 m1_daily / m2_daily 에 채운다.

왜 필요한가
-----------
지금까지 좌석점유율을 `관객 ÷ (상영횟수 × 160석)` 으로 **근사**해 왔다. 160석은
가정값이라 실제와 어긋난다 — 8/11 하츄핑은 근사 7.96% vs 실제 11.9% 로 33% 차이.
KOBIS 는 실제 좌석수와 좌석판매율을 매일 그대로 제공하므로 그걸 쓴다.

엔드포인트
----------
POST /kobis/business/stat/boxs/findDailySeatTicketList.do
  CSRFToken(빈 GET 에서), loadEnd=0, dmlMode=search,
  startDate=endDate=YYYY-MM-DD   ← sSearchFrom/sSearchTo 가 아니다. 그걸 쓰면
                                    날짜가 무시되고 늘 최근일이 돌아온다 (한번 당했다)
표 컬럼: 순위·영화명·개봉일·좌석판매율·좌석점유율·좌석수·매출액·누적매출액·관객수·누적관객수

채우는 열
---------
  seats       실제 좌석수 (그날 하츄핑이 판 수 있었던 자리)
  seat_sale   좌석판매율 = 관객 ÷ 좌석수      ← 수요의 질
  seat_share  좌석점유율 = 하츄핑 좌석 ÷ 전국 좌석  ← 공급에서 차지한 몫
기존 seat_rate(160석 근사)는 손대지 않고 남겨 둔다.

이미 값이 있는 행은 건너뛰므로, 매일 돌리면 새 날짜 1건만 받는다.
1편 141일 백필은 첫 실행에서 한 번만 일어난다.

    python kobis_seats.py [--refresh-last N] [--no-push]
"""
import csv
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

REPO = Path(__file__).resolve().parent
DATA = REPO / "data" / "hatchuping"
URL = ("https://www.kobis.or.kr/kobis/business/stat/boxs/"
       "findDailySeatTicketList.do")
TITLE_KEY = "하츄핑"
NEW_COLS = ["seats", "seat_sale", "seat_share"]
SLEEP = 0.35

FILES = [("m1_daily.csv", date(2024, 8, 7)), ("m2_daily.csv", date(2026, 8, 5))]


def _num(s):
    s = re.sub(r"[^0-9]", "", str(s))
    return int(s) if s else 0


def _pct(s):
    m = re.search(r"([0-9.]+)", str(s))
    return round(float(m.group(1)) / 100, 4) if m else ""


def _trs(t):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        yield [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def fetch(day: date, open_date: date):
    """그날 하츄핑 행에서 (좌석수, 좌석판매율, 좌석점유율). 없으면 None."""
    last = None
    for attempt in range(4):            # KOBIS 는 이따금 연결을 끊는다 (10054)
        try:
            s = requests.Session()
            s.headers["User-Agent"] = "Mozilla/5.0"
            g = s.get(URL, timeout=30)
            g.encoding = g.apparent_encoding or "utf-8"
            tok = re.search(r'name="CSRFToken"\s+value="([^"]+)"', g.text)
            r = s.post(URL, data={
                "CSRFToken": tok.group(1) if tok else "", "loadEnd": "0",
                "dmlMode": "search", "startDate": day.isoformat(),
                "endDate": day.isoformat(), "searchType": "",
                "repNationCd": "", "wideareaCd": "",
                "sMovName": "", "sMovLang": "ko"}, timeout=30)
            r.encoding = r.apparent_encoding or "utf-8"
            break
        except requests.exceptions.ConnectionError as e:
            last = e
            time.sleep(5 * (attempt + 1))
    else:
        raise last

    for c in _trs(r.text):
        if len(c) >= 10 and TITLE_KEY in c[1] and c[2] == open_date.isoformat():
            return {"seats": _num(c[5]), "seat_sale": _pct(c[3]),
                    "seat_share": _pct(c[4])}
    return None


def process(name, open_date, refresh_last=0):
    path = DATA / name
    if not path.exists():
        print(f"{name}: 없음 — 건너뜀")
        return 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    head = list(rows[0].keys()) if rows else []
    for c in NEW_COLS:
        if c not in head:
            head.append(c)

    # 마지막 N일은 KOBIS 가 수치를 나중에 고치는 일이 있어 다시 받는다
    refresh_from = len(rows) - refresh_last if refresh_last else len(rows)
    todo = [(i, r) for i, r in enumerate(rows)
            if not str(r.get("seats") or "").strip() or i >= refresh_from]
    if not todo:
        print(f"{name}: 이미 최신 ({len(rows)}행)")
        return 0

    print(f"{name}: {len(todo)}일치 수집 (전체 {len(rows)}행)")
    got = 0
    for n, (i, r) in enumerate(todo, 1):
        try:
            d = datetime.strptime(str(r["date"])[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        try:
            v = fetch(d, open_date)
        except Exception as e:
            print(f"   {d}: 실패 {type(e).__name__} — 건너뜀")
            continue
        if v:
            rows[i].update(v)
            got += 1
        else:
            rows[i].setdefault("seats", "")
        if n % 25 == 0:
            print(f"   {n}/{len(todo)} …")
        time.sleep(SLEEP)

    for r in rows:                       # 새 열이 없는 행은 빈 값으로 맞춘다
        for c in NEW_COLS:
            r.setdefault(c, "")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {got}일 채움")
    return got


def main():
    args = sys.argv[1:]
    n = 0
    if "--refresh-last" in args:
        n = int(args[args.index("--refresh-last") + 1])
    total = sum(process(name, od, refresh_last=n) for name, od in FILES)
    if not total or "--no-push" in args:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"kobis seats {date.today()}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])


if __name__ == "__main__":
    main()
