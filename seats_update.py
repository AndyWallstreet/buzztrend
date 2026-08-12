# -*- coding: utf-8 -*-
"""극장 예매 좌석 추적 — CGV + 롯데시네마 회차별 '팔린 좌석'으로 주말을 직접 잰다.

KOBIS 예매관객수는 앞으로의 모든 회차를 뭉뚱그린 한 덩어리라 '토요일이
어떤가'를 못 뽑는다. 극장 예매 API 는 회차별 좌석을 주므로 날짜를 찍어 볼 수 있다.

API
---
CGV   GET  cgv.co.kr/api/v1/booking/searchMovScnInfo?coCd=A420&siteNo=&scnYmd=YYYYMMDD&rtctlScopCd=08
      극장목록 cgv.co.kr/api/v1/content/site/searchAllRegionAndSite?coCd=A420
      좌석: cpSeatCnt(총) / frSeatCnt(잔여)  → 판매 = cp - fr
      ※ 예전 www.cgv.co.kr 은 python 을 403 으로 막지만, 신규 cgv.co.kr/api/v1 은 열려 있다.

롯데  POST lottecinema.co.kr/LCWS/Ticketing/TicketingData.aspx (multipart paramList)
      MethodName=GetPlaySequence, playDate, cinemaID="{Div}|{Detail}|{ID}"
      극장목록 /LCWS/Cinema/CinemaData.aspx GetCinemaItems
      좌석: TotalSeatCount(총) / BookingSeatCount(**잔여**, 이름과 반대) → 판매 = Total - Booking
      검증: 화면 '매진' 회차가 BookingSeatCount=0, IsBookingYN='E' 였고
            같은 화면 '잔여석 133/295' 회차가 API 에서도 133.

가장 중요한 한계 — 주말 상영표는 목요일쯤 열린다
------------------------------------------------
수요일에 토요일을 조회하면 극장 상당수가 아직 편성을 안 올렸다. 그때
판매율을 그대로 믿으면 '공개된 회차 몇 개'만 재게 되어 크게 왜곡된다.
그래서 published(그날 하츄핑 편성이 있는 표본 극장 수)를 함께 남기고,
표본의 절반 아래면 신뢰 불가로 표시한다. 비교는 반드시 **같은 리드타임끼리**
— '금요일 아침에 본 토요일' 대 '지난 금요일 아침에 본 지난 토요일'.

    python seats_update.py [--build-panel] [--no-push]
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
TITLE_KEY = "하츄핑"
PANEL_SIZE = 20          # 전국을 매일 두드리지 않는다 — 추세만 보면 되니 고정 표본
DAYS_AHEAD = 5
SLEEP = 0.3
HEAD = ["ts", "chain", "asof", "target", "dow", "lead", "panel", "published",
        "shows", "seats", "sold", "fill"]


# ============================== CGV ==============================
CGV_H = {"User-Agent": UA, "Referer": "https://cgv.co.kr/cnm/movieBook/cinema",
         "Accept": "application/json, text/plain, */*"}


def cgv_sites():
    r = requests.get("https://cgv.co.kr/api/v1/content/site/searchAllRegionAndSite"
                     "?coCd=A420", headers=CGV_H, timeout=30)
    out, seen = [], set()

    def walk(o):                       # 응답 구조가 바뀌어도 siteNo/siteNm 쌍만 건지면 된다
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            no, nm = o.get("siteNo"), o.get("siteNm") or o.get("siteNmKor")
            if no and nm and str(no) not in seen:
                seen.add(str(no))
                out.append({"id": str(no), "name": str(nm)})
            [walk(v) for v in o.values()]
    walk(r.json())
    return out


def cgv_shows(site_id, day):
    r = requests.get("https://cgv.co.kr/api/v1/booking/searchMovScnInfo",
                     params={"coCd": "A420", "siteNo": site_id,
                             "scnYmd": day.strftime("%Y%m%d"), "rtctlScopCd": "08"},
                     headers=CGV_H, timeout=30)
    rows = r.json().get("data") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    mine = [x for x in rows if isinstance(x, dict)
            and TITLE_KEY in str(x.get("prodNm") or x.get("movNm") or "")]
    seats = sum(int(x.get("cpSeatCnt") or x.get("stcnt") or 0) for x in mine)
    rest = sum(int(x.get("frSeatCnt") or 0) for x in mine)
    return len(mine), seats, seats - rest


# ============================ 롯데시네마 ============================
LOT = "https://www.lottecinema.co.kr/LCWS/"
LOT_H = {"User-Agent": UA, "Referer": "https://www.lottecinema.co.kr/NLCHS/Ticketing"}


def _lot(path, param):
    r = requests.post(LOT + path,
                      files={"paramList": (None, json.dumps(param, ensure_ascii=False))},
                      headers=LOT_H, timeout=30)
    r.encoding = "utf-8"
    return r.json()


def lotte_sites():
    j = _lot("Cinema/CinemaData.aspx",
             {"MethodName": "GetCinemaItems", "channelType": "HO",
              "osType": "W", "osVersion": UA})
    return [{"id": f"{c['DivisionCode']}|{c['DetailDivisionCode']}|{c['CinemaID']}",
             "name": c["CinemaNameKR"]}
            for c in (j.get("Cinemas") or {}).get("Items", [])]


def lotte_shows(cid, day):
    j = _lot("Ticketing/TicketingData.aspx",
             {"MethodName": "GetPlaySequence", "channelType": "HO", "osType": "W",
              "osVersion": UA, "playDate": day.isoformat(), "cinemaID": cid,
              "representationMovieCode": ""})
    items = (j.get("PlaySeqs") or {}).get("Items", [])
    mine = [i for i in items if TITLE_KEY in str(i.get("MovieNameKR", ""))]
    seats = sum(int(i["TotalSeatCount"]) for i in mine)
    rest = sum(int(i["BookingSeatCount"]) for i in mine)   # 이름과 달리 '잔여석'
    return len(mine), seats, seats - rest


CHAINS = {"CGV": (cgv_sites, cgv_shows), "롯데시네마": (lotte_sites, lotte_shows)}


# ============================== 공통 ==============================
def build_panel(chain, path):
    """오늘 하츄핑을 트는 극장 중 좌석 큰 순으로 표본을 고정한다.

    표본이 날마다 바뀌면 추세 비교가 무의미해지므로 파일로 얼려 둔다.
    """
    sites_fn, shows_fn = CHAINS[chain]
    today = date.today()
    sites = sites_fn()
    print(f"[{chain}] 전국 {len(sites)}곳 스캔 — 한 번만 돕니다")
    rows = []
    for n, s in enumerate(sites, 1):
        try:
            cnt, seats, _sold = shows_fn(s["id"], today)
        except Exception:
            continue
        if cnt:
            rows.append({"name": s["name"], "id": s["id"], "seats": seats})
        if n % 50 == 0:
            print(f"   {n}/{len(sites)} … 하츄핑 상영 {len(rows)}곳")
        time.sleep(SLEEP)
    rows.sort(key=lambda r: -r["seats"])
    panel = rows[:PANEL_SIZE]
    path.write_text(json.dumps({"chain": chain, "built": today.isoformat(),
                                "screening": len(rows), "panel": panel},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{chain}] 하츄핑 상영 {len(rows)}곳 중 표본 {len(panel)}곳 고정")
    return panel


def collect(chain, panel, today, ts):
    _sites_fn, shows_fn = CHAINS[chain]
    out = []
    for k in range(DAYS_AHEAD):
        tgt = today + timedelta(days=k)
        pub = n_shows = seats = sold = 0
        for c in panel:
            try:
                cnt, st, sd = shows_fn(c["id"], tgt)
            except Exception:
                continue
            if cnt:
                pub += 1
                n_shows += cnt
                seats += st
                sold += sd
            time.sleep(SLEEP)
        ok = pub >= len(panel) / 2
        out.append({"ts": ts, "chain": chain, "asof": today.isoformat(),
                    "target": tgt.isoformat(), "dow": "월화수목금토일"[tgt.weekday()],
                    "lead": k, "panel": len(panel), "published": pub,
                    "shows": n_shows, "seats": seats, "sold": sold,
                    "fill": round(sold / seats, 4) if seats else ""})
        print(f"  [{chain}] {tgt} ({out[-1]['dow']}) +{k}일: 편성 {pub}/{len(panel)}곳 · "
              f"{n_shows}회 · {sold:,}/{seats:,}"
              + (f" = {sold/seats:.1%}" if seats else "")
              + ("" if ok else "   ⚠ 편성 미공개 많음 — 판매율 신뢰 불가"))
    return out


def main():
    args = sys.argv[1:]
    today, ts = date.today(), time.strftime("%Y-%m-%d %H:%M")
    allrows = []
    for chain in CHAINS:
        pp = DATA / f"panel_{'cgv' if chain == 'CGV' else 'lotte'}.json"
        if "--build-panel" in args or not pp.exists():
            panel = build_panel(chain, pp)
        else:
            panel = json.loads(pp.read_text(encoding="utf-8"))["panel"]
        allrows += collect(chain, panel, today, ts)

    path = DATA / "seats.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f)]
    key = {(r["chain"], r["asof"], r["target"]) for r in allrows}
    rows = [r for r in rows if (r["chain"], r["asof"], r["target"]) not in key]
    rows.extend(allrows)
    rows.sort(key=lambda r: (r["asof"], r["chain"], r["target"]))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD)
        w.writeheader()
        w.writerows(rows)

    (DATA / "seats_now.json").write_text(json.dumps(
        {"ts": ts, "asof": today.isoformat(), "rows": allrows,
         "note": "판매=총좌석-잔여좌석 · published 가 표본 절반 미만이면 편성 미공개라 판매율 쓰지 말 것"},
        ensure_ascii=False, indent=2), encoding="utf-8")

    if "--no-push" in args:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"seats {today}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])


if __name__ == "__main__":
    main()
