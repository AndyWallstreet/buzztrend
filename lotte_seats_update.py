# -*- coding: utf-8 -*-
"""롯데시네마 회차별 좌석 판매 추적 — 주말 수요를 '표가 팔린 좌석'으로 직접 잰다.

KOBIS 예매관객수는 앞으로의 모든 회차를 뭉뚱그린 한 덩어리라 '토요일이
어떤가'를 못 뽑는다. 극장 예매 페이지는 회차별 좌석을 주므로 날짜를 찍어
볼 수 있다.

API (사이트가 자기 화면 그릴 때 쓰는 것과 같은 호출)
----------------------------------------------------
POST /LCWS/Ticketing/TicketingData.aspx  multipart 필드 paramList=<JSON>
  MethodName=GetPlaySequence, playDate=YYYY-MM-DD,
  cinemaID="{DivisionCode}|{DetailDivisionCode}|{CinemaID}"
극장 목록: POST /LCWS/Cinema/CinemaData.aspx  MethodName=GetCinemaItems (237곳)

좌석 필드 해석 — 여기서 한 번 틀렸다가 잡았다
---------------------------------------------
**BookingSeatCount = 잔여석**이다 (이름과 반대). 검증: 화면에 '매진'으로
뜬 회차(월드타워 8/12 21관 17:15)의 BookingSeatCount 가 0 이고 IsBookingYN='E'
였고, 같은 화면의 '잔여석 133/295' 회차가 API 에서도 133 이었다.
따라서  판매좌석 = TotalSeatCount - BookingSeatCount.

가장 중요한 한계 — 주말 상영표는 목요일쯤 열린다
------------------------------------------------
수요일에 토요일을 조회하면 극장 대부분이 아직 시간표를 안 올렸다. 표본
4곳의 8/15 전체 회차가 117->84, 36->15, 35->22, 59->22 로 무너지는데
이건 하츄핑이 빠진 게 아니라 **편성 자체가 미공개**라는 뜻이다. 이때
판매율을 그대로 믿으면 '공개된 회차 몇 개'만 재게 되어 크게 왜곡된다
(월드타워 8/16 이 91.6% 로 나온 이유).

그래서 이 스크립트는 판매율과 함께 **published**(그날 하츄핑 회차가 있는
표본 극장 수)를 같이 남긴다. published 가 표본의 절반 아래면 그 숫자는
쓰지 말 것. 비교는 반드시 **같은 리드타임끼리** — '금요일 아침에 본 토요일'
대 '지난 금요일 아침에 본 지난 토요일' 이라야 뜻이 있다.

    python lotte_seats_update.py [--build-panel] [--no-push]
"""
import csv
import json
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
BASE = "https://www.lottecinema.co.kr/LCWS/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
HDR = {"User-Agent": UA, "Referer": "https://www.lottecinema.co.kr/NLCHS/Ticketing"}

TITLE_KEY = "하츄핑"
PANEL_SIZE = 20                 # 전국 237곳을 매일 두드리지 않는다 — 추세만 보면 되니 고정 표본
DAYS_AHEAD = 5                  # 오늘 포함 5일 (주말이 항상 들어오게)
SLEEP = 0.35                    # 예의상 간격

HEAD = ["ts", "asof", "target", "dow", "lead", "panel", "published",
        "shows", "seats", "sold", "fill"]


def call(path, param, tries=3):
    last = None
    for k in range(tries):
        try:
            r = requests.post(BASE + path,
                              files={"paramList": (None, json.dumps(param, ensure_ascii=False))},
                              headers=HDR, timeout=30)
            r.encoding = "utf-8"
            return r.json()
        except Exception as e:                      # 네트워크 흔들림만 재시도
            last = e
            time.sleep(2 * (k + 1))
    raise last


def cinemas():
    j = call("Cinema/CinemaData.aspx",
             {"MethodName": "GetCinemaItems", "channelType": "HO",
              "osType": "W", "osVersion": UA})
    return (j.get("Cinemas") or {}).get("Items", [])


def cid_of(c):
    return f"{c['DivisionCode']}|{c['DetailDivisionCode']}|{c['CinemaID']}"


def shows(cid, day):
    """(하츄핑 회차들, 그 극장 그날 전체 회차수)."""
    j = call("Ticketing/TicketingData.aspx",
             {"MethodName": "GetPlaySequence", "channelType": "HO", "osType": "W",
              "osVersion": UA, "playDate": day.isoformat(), "cinemaID": cid,
              "representationMovieCode": ""})
    items = (j.get("PlaySeqs") or {}).get("Items", [])
    mine = [i for i in items if TITLE_KEY in str(i.get("MovieNameKR", ""))]
    return mine, len(items)


def build_panel(path):
    """오늘 하츄핑을 트는 극장 중 좌석이 큰 순으로 표본 고정.

    한 번만 전국을 훑는다(237회). 표본이 날마다 바뀌면 추세 비교가 무의미해지므로
    파일로 얼려 둔다.
    """
    today = date.today()
    rows = []
    all_c = cinemas()
    print(f"전국 {len(all_c)}곳 스캔 — 한 번만 돕니다")
    for n, c in enumerate(all_c, 1):
        try:
            mine, _ = shows(cid_of(c), today)
        except Exception:
            continue
        if mine:
            seats = sum(int(i["TotalSeatCount"]) for i in mine)
            rows.append({"name": c["CinemaNameKR"], "cid": cid_of(c), "seats": seats})
        if n % 40 == 0:
            print(f"   {n}/{len(all_c)} … 하츄핑 상영 {len(rows)}곳")
        time.sleep(SLEEP)
    rows.sort(key=lambda r: -r["seats"])
    panel = rows[:PANEL_SIZE]
    path.write_text(json.dumps({"built": today.isoformat(), "panel": panel},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"표본 {len(panel)}곳 고정 → {path.name}")
    return panel


def main():
    args = sys.argv[1:]
    ppath = DATA / "lotte_panel.json"
    if "--build-panel" in args or not ppath.exists():
        panel = build_panel(ppath)
    else:
        panel = json.loads(ppath.read_text(encoding="utf-8"))["panel"]

    today = date.today()
    ts = time.strftime("%Y-%m-%d %H:%M")
    out = []
    for k in range(DAYS_AHEAD):
        tgt = today + timedelta(days=k)
        pub = tot_shows = seats = sold = 0
        for c in panel:
            try:
                mine, _n = shows(c["cid"], tgt)
            except Exception:
                continue
            if mine:
                pub += 1
                tot_shows += len(mine)
                for i in mine:
                    t, rest = int(i["TotalSeatCount"]), int(i["BookingSeatCount"])
                    seats += t
                    sold += t - rest
            time.sleep(SLEEP)
        out.append({
            "ts": ts, "asof": today.isoformat(), "target": tgt.isoformat(),
            "dow": "월화수목금토일"[tgt.weekday()], "lead": k,
            "panel": len(panel), "published": pub, "shows": tot_shows,
            "seats": seats, "sold": sold,
            "fill": round(sold / seats, 4) if seats else "",
        })
        flag = "" if pub >= len(panel) / 2 else "  ⚠ 편성 미공개 많음 — 판매율 신뢰 불가"
        print(f"  {tgt} ({out[-1]['dow']}) lead+{k}: 표본 {pub}/{len(panel)}곳 공개 · "
              f"{tot_shows}회 · 좌석 {sold:,}/{seats:,}"
              + (f" = {sold/seats:.1%}" if seats else "") + flag)

    path = DATA / "lotte_seats.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f)]
    keep = {(r["asof"], r["target"]) for r in out}
    rows = [r for r in rows if (r["asof"], r["target"]) not in keep]   # 같은 날 재실행 = 덮어쓰기
    rows.extend(out)
    rows.sort(key=lambda r: (r["asof"], r["target"]))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD)
        w.writeheader()
        w.writerows(rows)

    (DATA / "lotte_seats_now.json").write_text(json.dumps({
        "ts": ts, "asof": today.isoformat(), "panel": len(panel), "rows": out,
        "note": "BookingSeatCount=잔여석 · 판매=Total-Booking · "
                "published 가 표본 절반 미만이면 편성 미공개라 판매율을 쓰면 안 됨",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if "--no-push" in args:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"lotte seats {today}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])


if __name__ == "__main__":
    main()
