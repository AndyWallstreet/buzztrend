# -*- coding: utf-8 -*-
"""KOBIS 실시간 예매율 스냅샷 — 개봉 후 '앞으로 들어올 관객' 추적.

왜 필요한가
-----------
개봉 후 확정 관객수(m2_daily.csv)는 **지나간 날**만 알려준다. 이번 주말이
어떨지는 다음 주 월요일 아침에야 안다. 예매관객수는 반대로 **아직 상영되지
않은 회차의 표**라서, 주말을 며칠 앞두고 미리 보인다.

핵심 지표는 예매관객수 자체가 아니라 **하루 신규 예매량**이다:

    어제 신규 예매 ≈ 오늘아침 예매 − 어제아침 예매 + 어제 실관객수

예매관객수 잔고는 표가 팔려서 늘고 상영돼서 줄기 때문에, 잔고만 보면
"잘 팔리는 날"과 "많이 상영한 날"이 구분되지 않는다. 위 식은 소진분을
되더해서 '어제 몇 명이 표를 샀나'만 남긴다 — 이게 관객수를 0~3일 앞선다.

한계 (화면에도 적어 둔다)
-------------------------
KOBIS 실시간 예매율은 **그 순간만** 제공하고 과거를 보관하지 않는다. 그래서
1편(2024)의 개봉 후 일별 예매관객수는 어디에도 없다 — 복구 불가능하다.
1편 예매 수치는 개봉 전 보도된 4개 시점(D-8·D-7·D-5·D-1)이 전부고 그건
이미 booking.csv/booking_meta.json 에 들어가 있다. 따라서 개봉 후 구간의
1편 대비 비교는 **실관객수 배수**로 하고, 예매는 '앞을 보는 창'으로만 쓴다.

수집 시각을 고정하는 것이 중요하다 — 예매는 하루 종일 늘어나므로 아침
스냅샷끼리만 비교해야 의미가 있다. 매일 07:30 작업에서 함께 돌린다.

    python booking_live_update.py [--no-push]
"""
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

try:                                    # 사내 프록시 — verify=False 는 쓰지 않는다
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

REPO = Path(__file__).resolve().parent
DATA = REPO / "data" / "hatchuping"
URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findRealTicketList.do"

TITLE_KEY = "하츄핑"
OPEN2 = date(2026, 8, 5)
TOP_N = 10                              # 경쟁작 예매도 같이 — 주말 파이를 누가 가져가나

SNAP_HEAD = ["ts", "date", "time", "rank", "rate", "tickets", "cum",
             "total_tickets", "share", "top1_title", "top1_tickets",
             "top2_title", "top2_tickets"]
RIVAL_HEAD = ["ts", "date", "rank", "title", "open", "rate", "tickets", "cum"]


def _num(s):
    s = re.sub(r"[^0-9-]", "", str(s))
    return int(s) if s not in ("", "-") else 0


def _pct(s):
    m = re.search(r"([0-9.]+)", str(s))
    return float(m.group(1)) if m else None


def _trs(text):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        yield [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def fetch():
    """(조회일시, [행...]) — 행 = 순위·영화명·개봉일·예매율·예매매출·누적매출·예매관객·누적관객.

    빈 GET 으로 CSRFToken 을 받고 POST 해야 표가 채워져 온다 (GET 만 하면 헤더만 온다).
    """
    last_err = None
    for attempt in range(4):            # KOBIS 는 이따금 연결을 끊는다 (10054)
        try:
            s = requests.Session()
            s.headers["User-Agent"] = "Mozilla/5.0"
            g = s.get(URL, timeout=30)
            g.encoding = g.apparent_encoding or "utf-8"
            tok = re.search(r'name="CSRFToken"\s+value="([^"]+)"', g.text)
            data = {"loadEnd": "0", "searchType": "search", "sMultiMovieYn": "",
                    "sRepNationCd": "", "sWideAreaCd": ""}
            if tok:
                data["CSRFToken"] = tok.group(1)
            r = s.post(URL, data=data, timeout=30)
            r.encoding = r.apparent_encoding or "utf-8"
            break
        except requests.exceptions.ConnectionError as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    else:
        raise last_err

    m = re.search(r"조회일시[^0-9]*([0-9]{4}/[0-9]{2}/[0-9]{2}\s+[0-9]{2}:[0-9]{2})", r.text)
    stamp = m.group(1) if m else None

    rows = []
    for c in _trs(r.text):
        if len(c) < 8 or not c[0].isdigit():
            continue
        rows.append({"rank": int(c[0]), "title": c[1], "open": c[2],
                     "rate": _pct(c[3]), "tickets": _num(c[6]), "cum": _num(c[7])})
    return stamp, rows


def _read(path, head):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)]


def _write(path, head, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader()
        w.writerows(rows)


def main():
    args = sys.argv[1:]
    stamp, rows = fetch()
    if not rows:
        print("실시간 예매율 표가 비어 있습니다 — 건너뜁니다")
        return

    mine = next((r for r in rows
                 if TITLE_KEY in r["title"] and r["open"] == OPEN2.isoformat()), None)
    if mine is None:
        print(f"'{TITLE_KEY}' 행이 없습니다 (총 {len(rows)}편) — 예매 마감/집계 중일 수 있습니다")
        return

    now = datetime.now()
    if stamp:                           # 서버가 준 조회일시를 우선 (이 PC 시계는 어긋난 적이 있다)
        try:
            now = datetime.strptime(stamp, "%Y/%m/%d %H:%M")
        except ValueError:
            pass
    ts = now.strftime("%Y-%m-%d %H:%M")
    d = now.date().isoformat()

    total = sum(r["tickets"] for r in rows)
    top = sorted(rows, key=lambda r: -r["tickets"])[:2]

    # ---- 1. 스냅샷 로그 (하루 여러 번 돌려도 전부 남긴다 — 시각별 곡선도 보고 싶으니)
    snap_path = DATA / "booking_live.csv"
    snaps = _read(snap_path, SNAP_HEAD)
    snaps = [s for s in snaps if s.get("ts") != ts]      # 같은 조회일시면 덮어쓰기
    snaps.append({
        "ts": ts, "date": d, "time": now.strftime("%H:%M"),
        "rank": mine["rank"], "rate": mine["rate"], "tickets": mine["tickets"],
        "cum": mine["cum"], "total_tickets": total,
        "share": round(mine["tickets"] / total, 5) if total else "",
        "top1_title": top[0]["title"][:18] if top else "",
        "top1_tickets": top[0]["tickets"] if top else "",
        "top2_title": top[1]["title"][:18] if len(top) > 1 else "",
        "top2_tickets": top[1]["tickets"] if len(top) > 1 else "",
    })
    snaps.sort(key=lambda s: s["ts"])
    _write(snap_path, SNAP_HEAD, snaps)

    # ---- 2. 경쟁작 예매 상위 N — 주말 파이를 누가 선점하고 있나
    riv_path = DATA / "booking_rivals.csv"
    rivals = _read(riv_path, RIVAL_HEAD)
    rivals = [r for r in rivals if r.get("ts") != ts]
    for r in sorted(rows, key=lambda r: -r["tickets"])[:TOP_N]:
        rivals.append({"ts": ts, "date": d, "rank": r["rank"], "title": r["title"],
                       "open": r["open"], "rate": r["rate"],
                       "tickets": r["tickets"], "cum": r["cum"]})
    rivals.sort(key=lambda r: (r["ts"], int(r["rank"])))
    _write(riv_path, RIVAL_HEAD, rivals)

    # ---- 3. 하루 신규 예매량 — 잔고 차이에 소진분(실관객)을 되더한 값.
    # 아침 스냅샷끼리만 비교해야 의미가 있어서 날짜별 '가장 이른' 스냅샷만 쓴다.
    morning = {}
    for s in snaps:
        if s["date"] not in morning or s["time"] < morning[s["date"]]["time"]:
            morning[s["date"]] = s

    adm = {}
    m2 = DATA / "m2_daily.csv"
    if m2.exists():
        with m2.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                adm[r["date"]] = int(r["adm"])

    daily = []
    days = sorted(morning)
    for prev, cur in zip(days, days[1:]):
        b0, b1 = int(morning[prev]["tickets"]), int(morning[cur]["tickets"])
        used = adm.get(prev)             # prev 날 실관객 = 그날 소진된 예매+현매
        daily.append({
            "date": prev, "booking_am": b0, "next_am": b1,
            "adm": used if used is not None else "",
            "new_booking": (b1 - b0 + used) if used is not None else "",
            "delta": b1 - b0,
        })
    _write(DATA / "booking_flow.csv",
           ["date", "booking_am", "next_am", "adm", "new_booking", "delta"], daily)

    # ---- 4. 화면용 스냅샷
    (DATA / "booking_live_now.json").write_text(json.dumps({
        "ts": ts, "date": d,
        "rank": mine["rank"], "rate": mine["rate"],
        "tickets": mine["tickets"], "cum": mine["cum"],
        "total_tickets": total,
        "share": round(mine["tickets"] / total, 5) if total else None,
        "rivals": [{"title": r["title"], "rate": r["rate"], "tickets": r["tickets"]}
                   for r in sorted(rows, key=lambda r: -r["tickets"])[:5]],
        "note": "KOBIS 실시간 예매율은 과거를 보관하지 않아 1편(2024) 개봉 후 예매는 존재하지 않음",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"예매 스냅샷 {ts} — 하츄핑 {mine['rank']}위 · 예매율 {mine['rate']}% · "
          f"예매관객 {mine['tickets']:,}명 (전체 {total:,}명 중 {mine['tickets']/total:.1%})")
    for r in sorted(rows, key=lambda r: -r["tickets"])[:5]:
        print(f"   · {r['title'][:20]}: {r['rate']}% / {r['tickets']:,}명")
    if daily:
        f = daily[-1]
        if f["new_booking"] != "":
            print(f"   · {f['date']} 신규 예매 {f['new_booking']:,}명 "
                  f"(잔고 {f['delta']:+,} + 실관객 {f['adm']:,})")
    else:
        print("   · 신규 예매량은 내일 아침 스냅샷이 하나 더 쌓이면 계산됩니다")

    if "--no-push" in args:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"booking snapshot {ts}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
        else:
            print("git: 새로 커밋할 것 없음")


if __name__ == "__main__":
    main()
