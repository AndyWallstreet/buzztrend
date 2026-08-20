# -*- coding: utf-8 -*-
"""YG 투어 예매 스냅샷 기록 → data/yg/*_booking.csv 에 한 줄 추가 + git push.

사용법:
  python yg_booking_update.py --city Goyang --status 매진 --source <기사URL>
  python yg_booking_update.py --city Taipei --sold 37000
  python yg_booking_update.py --artist babymonster --city Osaka --sold 80000 --source interpark --note "2차 티켓팅"

- 숫자를 아는 스탑은 --sold, 숫자를 못 구하는 예매처(쿠팡플레이 등)는 --status 로 기록.
  status 값: 매진 / 추가판매 / 판매중 / 미오픈 (페이지에서 뱃지로 표시)
- 총좌석(seats_total)은 투어 CSV 에서 도시 이름으로 자동으로 찾는다 (--total 로 덮어쓰기 가능).
- 같은 날 같은 도시를 다시 기록하면 그 줄을 덮어쓴다 (하루 1줄).
"""
import argparse
import csv
import subprocess
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "yg"
FILES = {"bigbang": ("bigbang_tour.csv", "bigbang_booking.csv"),
         "babymonster": ("babymonster_tour.csv", "babymonster_booking.csv")}
COLS = ["asof", "tour_date", "city", "seats_total", "seats_sold", "fill", "status",
        "source", "note"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artist", default="bigbang", choices=list(FILES))
    ap.add_argument("--city", required=True)
    ap.add_argument("--sold", type=int, help="판매된 좌석수 (숫자를 알 때)")
    ap.add_argument("--status", default="",
                    help="매진 / 추가판매 / 판매중 / 미오픈 (숫자를 못 구할 때)")
    ap.add_argument("--total", type=int, help="총좌석 (생략시 투어 CSV 에서 찾음)")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--source", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    tour_csv, booking_csv = FILES[a.artist]
    with (DATA / tour_csv).open(encoding="utf-8-sig") as f:
        stops = {r["city"].lower(): r for r in csv.DictReader(f)}
    stop = stops.get(a.city.lower())
    if stop is None:
        raise SystemExit(f"'{a.city}' 를 투어 캘린더에서 못 찾음. 있는 도시: "
                         + ", ".join(r["city"] for r in stops.values()))

    if a.sold is None and not a.status:
        raise SystemExit("--sold(좌석수) 또는 --status(매진 등) 중 하나는 필요합니다")

    total = a.total or int(stop["seats"])
    row = {"asof": a.asof, "tour_date": stop["date"], "city": stop["city"],
           "seats_total": total if a.sold is not None else "",
           "seats_sold": a.sold if a.sold is not None else "",
           "fill": round(a.sold / total, 4) if a.sold is not None else "",
           "status": a.status, "source": a.source, "note": a.note}

    p = DATA / booking_csv
    rows = []
    if p.exists() and p.stat().st_size > 10:
        with p.open(encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f)
                    if not (r["asof"] == a.asof and r["city"] == stop["city"])]
    rows.append({k: str(v) for k, v in row.items()})
    rows.sort(key=lambda r: (r["asof"], r["city"]))
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    what = (f"{a.sold:,}/{total:,}석 ({a.sold / total:.1%})"
            if a.sold is not None else a.status)
    print(f"{booking_csv}: {stop['city']} {a.asof} — {what}")

    repo = Path(__file__).resolve().parent
    subprocess.run(["git", "-C", str(repo), "add", str(p)], check=True)
    r = subprocess.run(["git", "-C", str(repo), "commit", "-m",
                        f"yg booking {a.artist} {stop['city']} {a.asof}"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        subprocess.run(["git", "-C", str(repo), "push"], check=True)
        print("git push: ok")
    else:
        print("git: 변경 없음 (커밋 생략)")


if __name__ == "__main__":
    main()
