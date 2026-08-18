"""개봉 후 일별 관객수 추적 — 하츄핑 2편 vs 1편 같은 일차 비교.

개봉 전에는 예매율(hatchuping_update.py)이 예측을 담당했지만, 개봉 후에는
KOBIS 일별 박스오피스의 '확정' 관객수가 유일한 진짜 숫자다. 이 스크립트는

  1편(2024-08-07 개봉) 일별 곡선을 자로 삼아
  '2편 N일차 ÷ 1편 N일차' 배수를 매일 계산하고
  그 배수 × 1편 최종 관객수(1,239,245) 를 최종 예상치로 쓴다.

억지 계수가 없다 — 1편 자기 곡선이 기준이라 관객이 빠지면 배수가 즉시 떨어진다.

사용법:
  python boxoffice_update.py                    # 2편 최신 확정일까지 갱신 + 사이트 파일 + push
  python boxoffice_update.py --build-m1         # 1편 기준 곡선 최초 생성 (한 번만)
  python boxoffice_update.py --build-m1-market  # 1편 경쟁작 점유율 백필 (한 번만, ~3분)
  python boxoffice_update.py --no-push          # git push 생략
"""
from __future__ import annotations

import csv
import html
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
# 경쟁작 추적 — 상영관 총량은 고정이라 오디세이·스파이더맨 같은 대작이 빠져야
# 하츄핑 상영횟수가 늘 수 있다. 그래서 상위 10편의 점유율을 통째로 쌓는다.
MARKET_HEAD = ["date", "day", "rank", "title", "open", "adm", "cum", "screens",
               "shows", "adm_share", "show_share", "screen_share"]
MARKET_TOP = 10
# 체인영화관별(CGV·롯데시네마·메가박스·씨네Q) 상영현황 — 어느 체인이 회차를 주는지.
# 점유율은 KOBIS 가 계산해 주는 값을 그대로 쓴다 (그 체인 전체 상영횟수 대비).
CHAINS_URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyMultichainList.do"
CHAIN_HEAD = ["date", "day", "rank", "title", "chain", "shows", "chain_shows",
              "show_share", "screens", "chain_screens", "screen_share"]
CHAIN_TOP = 10


def _num(s):
    s = re.sub(r"[^0-9-]", "", str(s))
    return int(s) if s not in ("", "-") else 0


def _clean_title(s):
    """영화명 셀에는 순위 증감 배지가 같이 들어온다 — '오디세이 8 상승', '파일럿 &nbsp; 동일'."""
    s = html.unescape(str(s)).replace("\xa0", " ")
    # 배지 숫자(몇 계단)는 항상 독립 토큰 — 공백을 요구해야 '베테랑2 하락'의 '2'를 안 깎는다
    s = re.sub(r"\s+(?:\d+\s+)?(동일|상승|하락|New)\s*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _post_day(url: str, day: date) -> str:
    last_err = None
    for attempt in range(4):          # KOBIS 가 이따금 연결을 끊는다 (10054) — 잠깐 쉬고 재시도
        try:
            r = requests.post(url, data={
                "loadEnd": "0", "searchType": "search",
                "sSearchFrom": day.isoformat(), "sSearchTo": day.isoformat(),
                "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.exceptions.ConnectionError as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise last_err


def _trs(text: str):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        yield [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def _fetch_rows(day: date):
    """그 날짜 박스오피스 표의 모든 영화 행을 컬럼 리스트로."""
    rows = []
    for c in _trs(_post_day(URL, day)):
        # 순위|영화명|개봉일|매출액|점유율|증감|누적매출|관객수|증감|누적관객|스크린|상영횟수
        if len(c) >= 12:
            rows.append(c)
    return rows


def fetch_day(day: date, open_date: date):
    """그 날짜 박스오피스에서 해당 영화 행 + 그날 시장 전체 합계를 dict 로. 없으면 None.

    점유율은 그날 상영된 **모든 영화**의 스크린/상영횟수 합계를 분모로 쓴다
    (업계에서 쓰는 방식 — 한 스크린에 여러 영화가 걸리므로 물리적 스크린 수와는 다르다).
    """
    hit, tot_scr, tot_shw = None, 0, 0
    for c in _fetch_rows(day):
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


def fetch_market(day: date, open_date: date):
    """그 날짜 상위 10편의 점유율 행들. open_date 는 우리 영화 개봉일 (경과일 계산용)."""
    rows = _fetch_rows(day)
    tot_scr = sum(_num(c[10]) for c in rows)
    tot_shw = sum(_num(c[11]) for c in rows)
    tot_adm = sum(_num(c[7]) for c in rows)
    out = []
    for c in rows:
        rank = _num(c[0])
        if rank == 0 or rank > MARKET_TOP:
            continue
        adm, scr, shw = _num(c[7]), _num(c[10]), _num(c[11])
        out.append({
            "date": day.isoformat(),
            "day": (day - open_date).days,
            "rank": rank,
            "title": _clean_title(c[1]),
            "open": c[2],
            "adm": adm,
            "cum": _num(c[9]),
            "screens": scr,
            "shows": shw,
            "adm_share": round(adm / tot_adm, 4) if tot_adm else "",
            "show_share": round(shw / tot_shw, 4) if tot_shw else "",
            "screen_share": round(scr / tot_scr, 4) if tot_scr else "",
        })
    return out


def _pct(s):
    s = re.sub(r"[^0-9.]", "", str(s))
    return round(float(s) / 100, 4) if s else ""


_chain_sess = None


def _chain_post(start: date, end_d: date) -> str:
    """체인별 통계는 CSRFToken + startDate/endDate 를 요구한다 — 박스오피스식
    sSearchFrom 은 조용히 무시되고 '최근 7일'이 온다 (2026-08-10 실측).
    세션으로 토큰을 한 번 받아 재사용하고, 끊기면 세션부터 다시 만든다."""
    global _chain_sess
    last_err = None
    for attempt in range(4):
        try:
            if _chain_sess is None:
                s = requests.Session()
                s.headers["User-Agent"] = "Mozilla/5.0"
                r = s.get(CHAINS_URL, timeout=30)
                r.encoding = r.apparent_encoding or "utf-8"
                m = re.search(r'name="CSRFToken"\s+value="([^"]+)"', r.text)
                _chain_sess = (s, m.group(1) if m else "")
            s, tok = _chain_sess
            r = s.post(CHAINS_URL, data={
                "CSRFToken": tok, "loadEnd": "0", "dmlMode": "search",
                "startDate": start.isoformat(), "endDate": end_d.isoformat(),
            }, timeout=30)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.exceptions.ConnectionError as e:
            last_err = e
            _chain_sess = None
            time.sleep(5 * (attempt + 1))
    raise last_err


def fetch_chains(start: date, end_d: date, open_date: date):
    """체인영화관별 상영현황을 [start, end_d] 구간(최대 7일)으로 받아 날짜별 dict 로.

    응답은 날짜별 섹션('2026년 08월 09일' 머리글)으로 나뉘고, 각 날짜 표는 영화 하나가
    13행(체인 4×직영/위탁/계 + 기타 + 전체)에 걸쳐 있으며 순위·영화명·체인명이 rowspan
    이라, 행 길이(10/8/7)로 수준을 구분하며 상태를 들고 간다. '계'(체인 합계)와
    기타·전체 행만 저장한다. 하루 상위 5편만 제공 — 그 밖으로 밀리면 그날 데이터는 없다.
    """
    text = _chain_post(start, end_d)
    parts = re.split(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일", text)
    out = {}
    # parts = [머리, y, m, d, 본문, y, m, d, 본문, ...]
    for i in range(1, len(parts) - 3, 4):
        sec_date = date(int(parts[i]), int(parts[i + 1]), int(parts[i + 2]))
        body = parts[i + 3]
        rows = []
        rank, title, chain = None, None, None
        for c in _trs(body):
            if not c or c[0] == "순위":
                continue
            rec = None
            if len(c) == 10:        # 새 영화의 첫 행: 순위|영화명|체인|구분|숫자 6칸
                rank, title, chain = _num(c[0]), _clean_title(c[1]), c[2]
                rec = (c[3], c[4:])
            elif len(c) == 8:       # 같은 영화의 다음 체인: 체인|구분|숫자 6칸
                chain, rec = c[0], (c[1], c[2:])
            elif len(c) == 7:       # 이어지는 행: 위탁/계, 또는 기타/전체
                if c[0] in ("기타", "전체"):
                    chain, rec = c[0], ("계", c[1:])
                else:
                    rec = (c[0], c[1:])
            if rec is None or rank is None or rank == 0 or rank > CHAIN_TOP:
                continue
            gubun, v = rec
            if gubun != "계" or len(v) < 6:
                continue
            rows.append({
                "date": sec_date.isoformat(),
                "day": (sec_date - open_date).days,
                "rank": rank,
                "title": title,
                "chain": chain,
                "shows": _num(v[0]),
                "chain_shows": _num(v[1]),
                "show_share": _pct(v[2]),
                "screens": _num(v[3]),
                "chain_screens": _num(v[4]),
                "screen_share": _pct(v[5]),
            })
        if rows:
            out[sec_date.isoformat()] = rows
    return out


def build_chains(path: Path, open_date: date, end: date, refresh_last=0):
    """한 요청이 최대 7일을 덮으므로 7일 창 단위로 필요한 구간만 받는다."""
    by_date = read_market(path)          # date -> rows (제너릭이라 그대로 재사용)
    recent = {(end - timedelta(days=i)).isoformat() for i in range(refresh_last)}

    def need(d):
        k = d.isoformat()
        return k not in by_date or k in recent

    added, w_start = 0, open_date
    while w_start <= end:
        w_end = min(w_start + timedelta(days=6), end)
        if any(need(w_start + timedelta(days=i))
               for i in range((w_end - w_start).days + 1)):
            time.sleep(0.8)   # 예의상 간격 — 빠른 연속 요청은 IP 차단을 부른다
            got = fetch_chains(w_start, w_end, open_date)
            for k, rows in got.items():
                if open_date.isoformat() <= k <= end.isoformat() and need(date.fromisoformat(k)):
                    by_date[k] = rows
                    added += 1
        w_start = w_end + timedelta(days=1)

    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CHAIN_HEAD)
        w.writeheader()
        for k in sorted(by_date):
            for row in by_date[k]:
                w.writerow(row)
    print(f"{path.name}: {len(by_date)}일치 (이번에 {added}일 갱신)")
    return by_date


def read_market(path: Path):
    """date -> [row dict] (제목에 쉼표가 들어갈 수 있어 csv 모듈로 읽고 쓴다)."""
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["date"], []).append(row)
    return out


def write_market(path: Path, by_date: dict):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MARKET_HEAD)
        w.writeheader()
        for k in sorted(by_date):
            for row in sorted(by_date[k], key=lambda r: int(r["rank"])):
                w.writerow(row)


def _unify_titles(by_date):
    """배지 정리의 한계 보정 — '슈퍼배드 4 상승'은 '슈퍼배드 4'+상승인지 '슈퍼배드'+4계단 상승인지
    글자만으로는 구분이 안 된다. 같은 개봉일에 'X'와 'X 4'가 둘 다 보이면 긴 쪽이 진짜 제목이다
    (깎여서 길어지는 경우는 없으므로)."""
    variants = {}
    for rows in by_date.values():
        for r in rows:
            variants.setdefault(r["open"], set()).add(r["title"])
    fix = {}
    for open_d, titles in variants.items():
        for t in titles:
            m = re.match(r"^(.+?)\s?\d+$", t)   # 'X 4'든 'X2'든 — 숫자 잘린 변형을 찾는다
            if m and m.group(1) in titles:
                fix[(open_d, m.group(1))] = t
    for rows in by_date.values():
        for r in rows:
            key = (r["open"], r["title"])
            if key in fix:
                r["title"] = fix[key]
    return by_date


def build_market(path: Path, open_date: date, end: date, refresh_last=0):
    """open_date~end 상위 10편 점유율을 채운다. 이미 있는 날은 건너뛰되 최근 refresh_last 일은 다시."""
    by_date = read_market(path)
    recent = {(end - timedelta(days=i)).isoformat() for i in range(refresh_last)}
    d, added = open_date, 0
    while d <= end:
        key = d.isoformat()
        if key in by_date and key not in recent:
            d += timedelta(days=1)
            continue
        time.sleep(0.8)   # 예의상 간격 — 빠른 연속 요청은 IP 차단을 부른다
        rows = fetch_market(d, open_date)
        if rows:
            by_date[key] = rows
            added += 1
        d += timedelta(days=1)
    by_date = _unify_titles(by_date)
    write_market(path, by_date)
    print(f"{path.name}: {len(by_date)}일치 (이번에 {added}일 갱신)")
    return by_date


def read_csv(path: Path):
    """파일에 실제로 적힌 헤더 그대로 읽는다.

    HEAD 로 고정해 zip 하면 kobis_seats.py 가 뒤에 붙여 둔 seats/seat_sale/
    seat_share 가 잘려 나가고, 이어지는 write_csv 에서 통째로 사라진다 —
    2026-08-18 아침에 실제로 사이트가 KeyError 로 죽었다. BOM 이 붙은 파일이
    있어 utf-8-sig 로 읽어야 첫 열 이름이 깨지지 않는다.
    """
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8-sig").strip().split("\n")
    if not lines:
        return {}
    head = [h.strip() for h in lines[0].split(",")] or list(HEAD)
    out = {}
    for line in lines[1:]:
        p = line.split(",")
        if p and p[0]:
            out[p[0]] = dict(zip(head, p))
    return out


def write_csv(path: Path, rows: dict):
    """HEAD 뒤에 다른 스크립트가 덧붙인 열이 있으면 그대로 보존해서 쓴다."""
    cols = list(HEAD)
    for r in rows.values():
        for k in r:
            if k not in cols:
                cols.append(k)
    lines = [",".join(cols)]
    for k in sorted(rows):
        r = rows[k]
        lines.append(",".join(str(r.get(h, "")) for h in cols))
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
            # 최근 며칠을 다시 받을 때 fetch_day 가 돌려주는 건 HEAD 열뿐이라,
            # 기존 행에 kobis_seats.py 가 채워 둔 열은 그대로 옮겨 싣는다.
            for k_extra, v in rows.get(key, {}).items():
                if k_extra not in row:
                    row[k_extra] = v
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

    if "--build-m1-market" in args:
        print("1편 경쟁작 점유율 백필 중 (2024-08-07 ~ 141일, 하루 한 요청)...")
        build_market(DATA / "m1_market.csv", M1_OPEN, M1_OPEN + timedelta(days=140))
        return

    if "--build-m1-chains" in args:
        print("1편 체인별 상영현황 백필 중 (2024-08-07 ~ 141일, 요청 하나가 7일 커버)...")
        build_chains(DATA / "m1_chains.csv", M1_OPEN, M1_OPEN + timedelta(days=140))
        return

    # ---- 2편: 어제 확정분까지 (KOBIS 는 다음날 아침에 전날을 확정한다)
    end = min(today - timedelta(days=1), today)
    if end < M2_OPEN:
        print("아직 개봉 전 — 할 일 없음")
        return
    m2 = build_curve(DATA / "m2_daily.csv", M2_OPEN, end, refresh_last=3,
                     force="--force" in args)
    market = build_market(DATA / "m2_market.csv", M2_OPEN, end, refresh_last=3)
    if market:
        top = sorted(market[max(market)], key=lambda r: int(r["rank"]))[:5]
        print("   · 상영점유율 top5: " + " · ".join(
            f"{r['title'][:12]} {float(r['show_share']):.1%}" for r in top if r["show_share"]))
    chains = build_chains(DATA / "m2_chains.csv", M2_OPEN, end, refresh_last=3)
    if chains:
        mine = [r for r in chains[max(chains)] if "하츄핑" in r["title"] and r["chain"] != "기타"]
        if mine:
            print("   · 하츄핑 체인별 상영점유율: " + " · ".join(
                f"{r['chain']} {float(r['show_share']):.1%}" for r in mine if r["show_share"]))
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
