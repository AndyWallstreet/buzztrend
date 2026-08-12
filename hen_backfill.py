# -*- coding: utf-8 -*-
"""마당을 나온 암탉(2011) 일별 곡선 백필 — 한국 애니 최고 흥행작(220만)을 비교 기준으로.

왜 이 영화인가
--------------
1편(124만)은 '같은 시리즈의 직전작'이라 가장 정확한 자(尺)지만, 천장이
어디인지는 알려 주지 않는다. 마당을 나온 암탉은 한국 창작 애니 실사
최고 기록(약 220만)이라 **'가능한 최대치가 어떤 모양이었나'** 를 보여 준다.

주의 — 개봉일은 2011-07-28 이다 (2011-07-27 행은 유료시사).
하츄핑처럼 유료시사가 누적에 먼저 잡혀 있어서, 배수를 볼 땐 그만큼 빼야 한다.

한계: **2011년 예매율은 어디에도 없다.** KOBIS 실시간 예매율은 그 순간만
제공하고 보관하지 않으므로 '사전예매율 → 실관객' 추적은 이 영화에 대해
불가능하다. 남아 있는 건 확정 관객수·스크린·상영횟수·좌석 통계다.

    python hen_backfill.py [--days 140] [--no-push]
"""
import csv
import html
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

REPO = Path(__file__).resolve().parent
DATA = REPO / "data" / "hatchuping"
OUT = DATA / "hen_daily.csv"

BOX = ("https://www.kobis.or.kr/kobis/business/stat/boxs/"
       "findDailyBoxOfficeList.do")
SEAT = ("https://www.kobis.or.kr/kobis/business/stat/boxs/"
        "findDailySeatTicketList.do")
OPEN = date(2011, 7, 28)
KEY = "암탉"
SEATS_PER_SHOW = 160
SLEEP = 0.3
HEAD = ["date", "day", "adm", "cum", "screens", "shows", "rank", "seat_rate",
        "total_screens", "total_shows", "screen_share", "show_share",
        "seats", "seat_sale", "seat_share"]


def _num(s):
    s = re.sub(r"[^0-9-]", "", str(s))
    return int(s) if s not in ("", "-") else 0


def _pct(s):
    m = re.search(r"([0-9.]+)", str(s))
    return round(float(m.group(1)) / 100, 4) if m else ""


def _trs(t):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        yield [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def _retry(fn, *a):
    last = None
    for k in range(4):                  # KOBIS 는 이따금 연결을 끊는다 (10054)
        try:
            return fn(*a)
        except requests.exceptions.ConnectionError as e:
            last = e
            time.sleep(4 * (k + 1))
    raise last


def _box(day):
    r = requests.post(BOX, data={
        "loadEnd": "0", "searchType": "search",
        "sSearchFrom": day.isoformat(), "sSearchTo": day.isoformat(),
        "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": ""},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.encoding = r.apparent_encoding or "utf-8"
    return list(_trs(r.text))


def _seat(day):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    g = s.get(SEAT, timeout=25)
    g.encoding = g.apparent_encoding or "utf-8"
    tok = re.search(r'name="CSRFToken"\s+value="([^"]+)"', g.text)
    r = s.post(SEAT, data={"CSRFToken": tok.group(1) if tok else "", "loadEnd": "0",
                           "dmlMode": "search", "startDate": day.isoformat(),
                           "endDate": day.isoformat(), "searchType": "",
                           "repNationCd": "", "wideareaCd": "",
                           "sMovName": "", "sMovLang": "ko"}, timeout=30)
    r.encoding = r.apparent_encoding or "utf-8"
    return list(_trs(r.text))


def fetch(day):
    """그날 암탉 행 + 시장 합계. 개봉일로 영화를 특정한다(동명이인 방지)."""
    rows = [c for c in _retry(_box, day) if len(c) >= 12]
    tot_scr = sum(_num(c[10]) for c in rows)
    tot_shw = sum(_num(c[11]) for c in rows)
    hit = None
    for c in rows:
        title = html.unescape(c[1]).replace("\xa0", " ")
        if KEY in title and c[2] == OPEN.isoformat():
            hit = c
            break
    if hit is None:
        return None
    adm, shows = _num(hit[7]), _num(hit[11])
    row = {
        "date": day.isoformat(), "day": (day - OPEN).days,
        "adm": adm, "cum": _num(hit[9]),
        "screens": _num(hit[10]), "shows": shows, "rank": _num(hit[0]),
        "seat_rate": round(adm / (shows * SEATS_PER_SHOW), 4) if shows else "",
        "total_screens": tot_scr, "total_shows": tot_shw,
        "screen_share": round(_num(hit[10]) / tot_scr, 4) if tot_scr else "",
        "show_share": round(shows / tot_shw, 4) if tot_shw else "",
        "seats": "", "seat_sale": "", "seat_share": "",
    }
    for c in _retry(_seat, day):
        if len(c) >= 10 and KEY in html.unescape(c[1]) and c[2] == OPEN.isoformat():
            row.update({"seats": _num(c[5]), "seat_sale": _pct(c[3]),
                        "seat_share": _pct(c[4])})
            break
    return row


def main():
    args = sys.argv[1:]
    days = 140
    if "--days" in args:
        days = int(args[args.index("--days") + 1])

    have = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8-sig", newline="") as f:
            have = {r["date"]: r for r in csv.DictReader(f)}

    got = miss = 0
    for k in range(days + 1):
        d = OPEN + timedelta(days=k)
        if d.isoformat() in have:
            continue
        try:
            r = fetch(d)
        except Exception as e:
            print(f"   D+{k} {d}: 실패 {type(e).__name__} — 중단")
            break
        if r:
            have[d.isoformat()] = r
            got += 1
            miss = 0
        else:
            miss += 1
            if miss >= 7:               # 일주일 내리 목록에 없으면 사실상 종영
                print(f"   D+{k} 부근에서 목록에서 사라짐 — 종료")
                break
        if k % 20 == 0:
            print(f"   D+{k} … 수집 {got}건")
        time.sleep(SLEEP)

    rows = sorted(have.values(), key=lambda r: r["date"])
    for r in rows:
        for c in HEAD:
            r.setdefault(c, "")
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    if rows:
        last = rows[-1]
        print(f"hen_daily.csv: {len(rows)}일 · 최종 누적 {int(last['cum']):,}명 "
              f"(D+{last['day']})")

    if "--no-push" in args or not got:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", "hen (마당을 나온 암탉) daily curve").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])


if __name__ == "__main__":
    main()
