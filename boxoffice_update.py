"""개봉 후 일별 관객수 추적 — 하츄핑 2편 vs 1편 같은 일차 비교.

개봉 전에는 예매율(hatchuping_update.py)이 예측을 담당했지만, 개봉 후에는
KOBIS 일별 박스오피스의 '확정' 관객수가 유일한 진짜 숫자다. 이 스크립트는

  1편(2024-08-07 개봉) 일별 곡선을 자로 삼아
  '2편 N일차 ÷ 1편 N일차' 배수를 매일 계산하고
  그 배수 × 1편 최종 관객수(1,239,245) 를 최종 예상치로 쓴다.

억지 계수가 없다 — 1편 자기 곡선이 기준이라 관객이 빠지면 배수가 즉시 떨어진다.

사용법:
  python boxoffice_update.py                # 2편 최신 확정일까지 갱신 + 사이트 파일 + push
  python boxoffice_update.py --build-m1     # 1편 기준 곡선 최초 생성 (한 번만)
  python boxoffice_update.py --no-push      # git push 생략
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import truststore

truststore.inject_into_ssl()

REPO = Path(__file__).parent
DATA = REPO / "data" / "hatchuping"

M1_OPEN = date(2024, 8, 7)          # 사랑의 하츄핑 (1편)
M2_OPEN = date(2026, 8, 5)          # 사랑의 하츄핑 2: 고래보석의 전설
M1_FINAL = 1239245                  # 1편 최종 관객수
SEATS_PER_SHOW = 160                # screens.json 과 같은 가정 (좌석점유율 근사용)

URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"
HEAD = ["date", "day", "adm", "cum", "screens", "shows", "rank", "seat_rate",
        "total_screens", "total_shows", "screen_share", "show_share"]


def _num(s):
    s = re.sub(r"[^0-9-]", "", str(s))
    return int(s) if s not in ("", "-") else 0


def fetch_day(day: date, open_date: date):
    """그 날짜 박스오피스에서 해당 영화 행 + 그날 시장 전체 합계를 dict 로. 없으면 None.

    점유율은 그날 상영된 **모든 영화**의 스크린/상영횟수 합계를 분모로 쓴다
    (업계에서 쓰는 방식 — 한 스크린에 여러 영화가 걸리므로 물리적 스크린 수와는 다르다).
    """
    last_err = None
    for attempt in range(4):          # KOBIS 가 이따금 연결을 끊는다 (10054) — 잠깐 쉬고 재시도
        try:
            r = requests.post(URL, data={
                "loadEnd": "0", "searchType": "search",
                "sSearchFrom": day.isoformat(), "sSearchTo": day.isoformat(),
                "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            break
        except requests.exceptions.ConnectionError as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    else:
        raise last_err
    r.encoding = r.apparent_encoding or "utf-8"

    hit, tot_scr, tot_shw = None, 0, 0
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
             for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        # 순위|영화명|개봉일|매출액|점유율|증감|누적매출|관객수|증감|누적관객|스크린|상영횟수
        if len(c) < 12:
            continue
        tot_scr += _num(c[10])
        tot_shw += _num(c[11])
        if "하츄핑" in c[1] and c[2] == open_date.isoformat():
            shows, adm = _num(c[11]), _num(c[7])
            hit = {
                "date": day.isoformat(),
                "day": (day - open_date).days,
                "adm": adm,
                "cum": _num(c[9]),
                "screens": _num(c[10]),
                "shows": shows,
                "rank": _num(c[0]),
                "seat_rate": round(adm / (shows * SEATS_PER_SHOW), 4) if shows else "",
            }
    if hit is None:
        return None
    hit["total_screens"] = tot_scr
    hit["total_shows"] = tot_shw
    hit["screen_share"] = round(hit["screens"] / tot_scr, 4) if tot_scr else ""
    hit["show_share"] = round(hit["shows"] / tot_shw, 4) if tot_shw else ""
    return hit


def read_csv(path: Path):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").strip().split("\n")[1:]:
        p = line.split(",")
        if p and p[0]:
            out[p[0]] = dict(zip(HEAD, p))
    return out


def write_csv(path: Path, rows: dict):
    lines = [",".join(HEAD)]
    for k in sorted(rows):
        r = rows[k]
        lines.append(",".join(str(r[h]) for h in HEAD))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_curve(path: Path, open_date: date, end: date, refresh_last=0, force=False):
    """open_date~end 구간을 채운다. 이미 있는 날은 건너뛰되 최근 refresh_last 일은 다시 받는다.

    force=True 면 전부 다시 받는다 (컬럼을 새로 추가했을 때 재구축용).
    """
    rows = {} if force else read_csv(path)
    have = set(rows)
    recent = {(end - timedelta(days=i)).isoformat() for i in range(refresh_last)}
    misses = 0
    d = open_date
    added = 0
    while d <= end:
        key = d.isoformat()
        if key in have and key not in recent:
            d += timedelta(days=1)
            continue
        time.sleep(0.8)   # 예의상 간격 — 빠른 연속 요청은 IP 차단을 부른다 (2026-08-07 실제로 당함)
        row = fetch_day(d, open_date)
        if row:
            rows[key] = row
            added += 1
            misses = 0
        else:
            misses += 1
            if misses >= 14 and d > open_date + timedelta(days=30):
                print(f"  {key} 이후 14일 연속 미상영 — 종료")
                break
        d += timedelta(days=1)
    write_csv(path, rows)
    print(f"{path.name}: {len(rows)}일치 (이번에 {added}일 갱신)")
    return rows


def preview_of(by_day):
    """유료시사 관객수 = 개봉일(D+0)의 누적 - 당일. 자료가 없으면 0."""
    d0 = by_day.get(0) if isinstance(next(iter(by_day), 0), int) else None
    if d0 is None:
        for v in by_day.values():
            if int(v["day"]) == 0:
                d0 = v
                break
    if not d0:
        return 0
    return max(0, int(d0["cum"]) - int(d0["adm"]))


def main():
    args = sys.argv[1:]
    today = date.today()

    if "--build-m1" in args:
        print("1편 기준 곡선 수집 중 (2024-08-07 ~)...")
        build_curve(DATA / "m1_daily.csv", M1_OPEN, M1_OPEN + timedelta(days=140),
                    force="--force" in args)
        return

    # ---- 2편: 어제 확정분까지 (KOBIS 는 다음날 아침에 전날을 확정한다)
    end = min(today - timedelta(days=1), today)
    if end < M2_OPEN:
        print("아직 개봉 전 — 할 일 없음")
        return
    m2 = build_curve(DATA / "m2_daily.csv", M2_OPEN, end, refresh_last=3,
                     force="--force" in args)
    m1 = read_csv(DATA / "m1_daily.csv")
    if not m2:
        print("2편 데이터 없음 (개봉일 확정 전일 수 있음)")
        return

    m1_by_day = {int(v["day"]): v for v in m1.values()}
    last = m2[max(m2)]
    dnum = int(last["day"])
    ref = m1_by_day.get(dnum)

    now = {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
        "last_date": last["date"],
        "day": dnum,
        "adm": int(last["adm"]),
        "cum": int(last["cum"]),
        "screens": int(last["screens"]),
        "shows": int(last["shows"]),
        "rank": int(last["rank"]),
        "seat_rate": float(last["seat_rate"]) if last["seat_rate"] else None,
        "m1_final": M1_FINAL,
    }
    if ref:
        # 유료시사 = 개봉일의 (누적 - 당일). 1편 49,683 vs 2편 27,410 으로 크게 달라서,
        # 생 누적끼리 비교하면 개봉 직후 2편이 실제보다 나빠 보인다 → 시사 제외분을 주 지표로.
        m2_pre = preview_of(m2)
        m1_pre = preview_of(m1_by_day)
        adj2 = int(last["cum"]) - m2_pre
        adj1 = int(ref["cum"]) - m1_pre
        ratio_adj = adj2 / max(1, adj1)
        ratio_cum = int(last["cum"]) / int(ref["cum"])
        ratio_day = int(last["adm"]) / max(1, int(ref["adm"]))
        now.update({
            "m1_cum": int(ref["cum"]),
            "m1_adm": int(ref["adm"]),
            "m1_screens": int(ref["screens"]),
            "m1_seat_rate": float(ref["seat_rate"]) if ref.get("seat_rate") else None,
            "m2_preview": m2_pre,
            "m1_preview": m1_pre,
            "adj_cum": adj2,
            "m1_adj_cum": adj1,
            "ratio_adj": round(ratio_adj, 4),
            "ratio_cum": round(ratio_cum, 4),
            "ratio_day": round(ratio_day, 4),
            "forecast": round(ratio_adj * M1_FINAL),
            "forecast_raw": round(ratio_cum * M1_FINAL),
        })
        print(f"D+{dnum} {last['date']}: 개봉 후 누적 {adj2:,}명 "
              f"(1편 {adj1:,}명) = {ratio_adj:.2f}배 "
              f"→ 최종 예상 {round(ratio_adj * M1_FINAL):,}명")
        print(f"   · 당일 {int(last['adm']):,}명 (1편 {int(ref['adm']):,}명) = {ratio_day:.2f}배"
              f" · 유료시사 2편 {m2_pre:,} / 1편 {m1_pre:,}")
    else:
        print(f"D+{dnum}: 1편 같은 일차 데이터 없음 — 배수 계산 생략")

    (DATA / "boxoffice_now.json").write_text(
        json.dumps(now, ensure_ascii=False, indent=2), encoding="utf-8")

    if "--no-push" in args:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"boxoffice update {last['date']} (D+{dnum})").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
        else:
            print("git: 새로 커밋할 것 없음")


if __name__ == "__main__":
    main()
