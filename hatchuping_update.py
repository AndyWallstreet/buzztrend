# -*- coding: utf-8 -*-
"""Daily updater — one command updates BOTH the Excel tracker and the website data.

Usage:
    python daily_update.py scrape.json

scrape.json format (numbers scraped from YouTube by the daily task):
{
  "date": "2026-07-24",
  "main":   {"ttv": {"views": 0, "likes": 0, "comments": 0},
             "byform": {"views": 0, "likes": 0, "comments": 0}},
  "teaser": {"ttv": {"views": 0, "likes": 0, "comments": 0},
             "byform": {"views": 0, "likes": 0, "comments": 0},
             "cns": {"views": 0, "likes": 0}},
  "sentiment": null   # or {"main_m2": [sp,p,neu,neg,sneg], "teaser_m2": [...], "note": "..."}
}

Which DATE a reading is filed under (same rule for YouTube and 예매):
    YouTube 조회수/좋아요/댓글도 '지금까지 누적'이라서, 아침(12시 전) 수집값은
    사실상 **어제 마감치**다. 그래서
      - 07:30 실행  -> 어제 행에 기록 (그 날의 확정 마감값. 전날 오후에 적어둔
                       잠정값을 덮어쓴다.) 오늘 행은 만들지 않는다.
      - 14:30 실행  -> 오늘 행에 기록 (장중 잠정값. 다음날 아침에 확정값으로 교체됨.)
    행은 '마지막 행인가'가 아니라 날짜로 찾는다 (find_row_by_date).

What it does, in order:
 1. Writes one row each to '메인 Daily' / '티저 Daily' / '댓글속도 Velocity'
    in Hatchuping2 tracker_v1.xlsx via Excel COM, on the date decided above.
    - If the user has the file open in Excel, it edits THAT open workbook
      (never quits their Excel, never touches their other workbooks).
    - Overwrites that date's row if it already exists (safe to re-run).
 2. Updates 2편 sentiment counts if provided.
 3. Recalculates, checks for formula errors, saves.
 4. Rewrites the website data files (data/*.csv, *.json) from the workbook.
 5. git add/commit/push (skips quietly if nothing changed or no remote).
"""
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pythoncom
import win32com.client

# Windows consoles default to cp949 here, which blows up on the Korean text and
# em-dashes in the progress messages. Force UTF-8 output instead.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

TRACKER =r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\SAMG 엔터\Hatchuping2 tracker_v1.xlsx"
BUZZ_XLSX = r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\SAMG 엔터\Heartuping movie 2_Buzz trend_v1.xlsx"
TRACKER_NAME = "Hatchuping2 tracker_v1.xlsx"
FORECAST = r"C:\Users\user99i1\Documents\하츄핑2_흥행예측.xlsx"
FORECAST_NAME = "하츄핑2_흥행예측.xlsx"
REPO = Path(__file__).parent            # the buzztrend repo
DATA = REPO / "data" / "hatchuping"     # site data for pages/1_🐳_하츄핑2_예고편.py
MAIN_RELEASE = date(2026, 7, 9)
TEASER_RELEASE = date(2026, 6, 15)

NUM = "#,##0"
DELTA = "+#,##0;-#,##0;0"
PCT = "0.0%"


def get_excel_and_wb(path=None, name=None):
    """Attach to the user's open Excel if the workbook is open there; else own instance.

    Defaults are resolved at CALL time, not import time — binding TRACKER as a
    default argument silently ignored any later override of the module constant,
    which let a test aimed at file copies edit the real workbook instead.
    """
    path = TRACKER if path is None else path
    name = TRACKER_NAME if name is None else name
    try:
        xl = win32com.client.GetActiveObject("Excel.Application")
        for w in xl.Workbooks:
            if w.Name == name:
                return xl, w, True
    except Exception:
        pass
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = xl.Workbooks.Open(path, UpdateLinks=0)
    return xl, wb, False


def last_data_row(ws, col=1, start=5):
    r, last = start, start - 1
    while ws.Cells(r, col).Value is not None:
        last = r
        r += 1
    return last


def find_row_by_date(ws, target, start=5):
    """(row, existed) for `target` — the existing row if there is one, else a fresh one.

    Keyed by date rather than 'is it the last row', because the 07:30 run rewrites
    YESTERDAY's row, which the previous 14:30 run has usually already created.
    """
    lr = last_data_row(ws, start=start)
    for r in range(start, lr + 1):
        v = ws.Cells(r, 1).Value
        if v is not None and hasattr(v, "date") and v.date() == target:
            return r, True
    return lr + 1, False


def fmt_row(ws, r, cols, fmt):
    ws.Range(ws.Cells(r, cols[0]), ws.Cells(r, cols[1])).NumberFormat = fmt


# 14:30까지의 증가분 → 하루 전체 환산 배수 (사용자 가정: 아침~14:30에 +1,000이면
# 하루 전체는 +2,500쯤 — 퇴근 후 저녁에 예매가 몰림). booking_log.csv가 며칠 쌓이면
# 실측으로 보정할 것.
AFTERNOON_FACTOR = 2.5


# 하루 예매 증가분이 시각별로 얼마나 들어와 있는지 (checkpoint 곡선).
# 사이 시각은 선형 보간 → 같은 날 몇 시에 읽어도 마감 추정치가 일관되게 나온다.
# 보수적으로 잡는다 — 늦게 잡을수록 추정 마감치가 내려간다:
#  - 07:30 = 0%   : 아침 수집값이 곧 어제 마감치 (정의).
#  - 14:30 = 42%  : 실측(7/30·7/31 로그) 28.7% / 42.3% 중 높은 쪽.
#                   (평균 40%로 잡으면 마감 추정이 더 커진다 → 보수적으로 42%)
#  - 23:00 = 100% : 예매 마감. 자정까지 계속 늘어난다고 보지 않는다.
DAY_SHARE = [(7.5, 0.0), (14.5, 0.42), (23.0, 1.0)]


def day_share(now):
    """지금(now)까지 오늘 예매 증가분의 몇 %가 들어와 있나."""
    h = now.hour + now.minute / 60
    if h <= DAY_SHARE[0][0]:
        return None                      # 아침 규칙이 따로 처리
    for (h0, s0), (h1, s1) in zip(DAY_SHARE, DAY_SHARE[1:]):
        if h <= h1:
            return s0 + (s1 - s0) * (h - h0) / (h1 - h0)
    return 1.0


def update_booking(d, booking):
    """KOBIS 실시간 예매율 → booking_log.csv / booking.csv / 흥행예측.xlsx '추적'.

    booking = {"tickets": 10963, "rate": 1.5, "rank": 6}

    핵심 규칙 — KOBIS 숫자는 '지금까지 누적'이라서:
    - 아침 수집(12시 전): 오늘 예매는 아직 없다시피 하므로 그 값은 **어제의 확정치**.
      오늘 값은 어제 하루 증가분만큼 더 오른다고 가정한 **추정치**로 만든다.
    - 오후 수집(12시 후): 아침 확정치와의 차이 = 오늘 지금까지 증가분.
      × AFTERNOON_FACTOR 로 하루 전체를 환산해 오늘 추정치를 갱신한다.
    """
    now = datetime.now()
    open_d = date(2026, 8, 5)

    # ---- 0. 원본 로그 (보정용 — 모든 수집값을 시각과 함께 남긴다)
    log = DATA / "booking_log.csv"
    if not log.exists():
        log.write_text("ts,tickets,rate,rank,note\n", encoding="utf-8")
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{now.strftime('%Y-%m-%d %H:%M')},{booking['tickets']},"
                f"{booking.get('rate', '')},{booking.get('rank', '')},\n")

    # ---- 1. booking.csv 다시 쓰기 (date,dday,tickets,rate,rank,kind)
    path = DATA / "booking.csv"
    rows = {}   # date -> [tickets, rate, rank, kind]
    for line in path.read_text(encoding="utf-8").strip().split("\n")[1:]:
        p = (line.split(",") + [""] * 6)[:6]
        if p[0]:
            rows[date.fromisoformat(p[0])] = [p[2], p[3], p[4], p[5] or "확정"]

    y = d - timedelta(days=1)
    morning = now.hour < 12
    if morning:
        # 이 값은 어제의 확정치
        rows[y] = [str(booking["tickets"]), str(booking.get("rate", "")),
                   str(booking.get("rank", "")), "확정"]
        prev_dates = sorted(dt for dt in rows if dt < y and rows[dt][3] != "추정")
        if prev_dates:
            p = prev_dates[-1]
            per_day = (booking["tickets"] - int(rows[p][0])) / max(1, (y - p).days)
        else:
            per_day = 0
        est = booking["tickets"] + round(per_day)
        est_note = "추정 (어제 증가분만큼 오른다고 가정)"
    else:
        # 오후: 아침에 적힌 어제 확정치 기준으로 오늘 속도를 환산.
        # 몇 시에 읽었는지에 따라 남은 시간이 다르므로 고정 배수(2.5) 대신
        # DAY_SHARE 곡선으로 '지금까지 들어온 비율'을 구해 하루치로 환산한다.
        base = int(rows[y][0]) if y in rows and rows[y][3] == "확정" else None
        share = day_share(now) or 1.0
        if base is not None and booking["tickets"] > base:
            add = booking["tickets"] - base
            est = base + round(add / share)
            hhmm = now.strftime("%H:%M")
            est_note = (f"추정 ({hhmm}까지 +{add:,} = 하루치의 {share:.0%} "
                        f"→ 마감 +{round(add / share):,})")
            # 교차검증 — 어제 하루 증가분을 그대로 오늘에 적용한 보수적 값
            prev_dates = sorted(dt for dt in rows if dt < y and rows[dt][3] != "추정")
            if prev_dates:
                p = prev_dates[-1]
                per_day = (base - int(rows[p][0])) / max(1, (y - p).days)
                est_note += f" · 어제증가분법 {base + round(per_day):,}"
        else:
            est = booking["tickets"]
            est_note = "추정 (오후 수집값 그대로 — 아침 확정치 없음)"
    rows[d] = [str(est), "", "", "추정"]

    # ---- 1b. 지금 이 순간의 실측값 (사이트 그래프에 '실시간' 점으로 찍는다)
    (DATA / "booking_now.json").write_text(json.dumps({
        "ts": now.strftime("%Y-%m-%d %H:%M"),
        "date": d.isoformat(),
        "dday": (open_d - d).days,
        "tickets": booking["tickets"],
        "rate": booking.get("rate"),
        "rank": booking.get("rank"),
        "est_close": est,
        "note": est_note,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["date,dday,tickets,rate,rank,kind"]
    for dt in sorted(rows):
        t, ra, rk, kind = rows[dt]
        lines.append(f"{dt.isoformat()},{(open_d - dt).days},{t},{ra},{rk},{kind}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"booking.csv updated — {y} 확정 반영, {d} 추정 {est:,} ({'아침' if morning else '오후'} 규칙)")

    # ---- 2. 흥행예측.xlsx '추적' — 어제 확정 + 오늘 추정, 날짜로 찾아서 쓴다
    pythoncom.CoInitialize()  # main()'s COM session may already be closed by now
    xl, wb, attached = get_excel_and_wb(FORECAST, FORECAST_NAME)
    prev_alerts, prev_screen = xl.DisplayAlerts, xl.ScreenUpdating
    xl.DisplayAlerts = False
    xl.ScreenUpdating = False
    try:
        ws = wb.Worksheets("추적")

        def find_or_append(target):
            lr = last_data_row(ws)
            for r in range(5, lr + 1):
                v = ws.Cells(r, 1).Value
                if v is not None and v.date() == target:
                    return r
            return lr + 1

        def write_row(target, tickets, note):
            n = find_or_append(target)
            ws.Cells(n, 1).Value = target.isoformat()
            ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
            if not str(ws.Cells(n, 2).Formula).startswith("=IF"):
                ws.Cells(n, 2).Formula = f'=IF(A{n}="","","D-"&TEXT($B$2-A{n},"0"))'
            ws.Cells(n, 3).Value = tickets
            ws.Cells(n, 3).NumberFormat = NUM
            ws.Cells(n, 4).Value = note
            for col in (1, 3, 4):
                ws.Cells(n, col).Font.Color = 0xFF0000  # blue (BGR) = input
            return n

        if morning:
            write_row(y, booking["tickets"],
                      f"확정 (다음날 아침 수집) · 예매율 {booking.get('rate', '?')}% · {booking.get('rank', '?')}위")
        n = write_row(d, est, est_note)
        xl.CalculateFull()
        wb.Save()
        print("forecast workbook saved (attached:", attached, ") row", n)
    finally:
        try:
            xl.DisplayAlerts = prev_alerts
            xl.ScreenUpdating = prev_screen
        except Exception:
            pass
        if not attached:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
            try:
                xl.Quit()
            except Exception:
                pass


def export_buzz():
    """Buzz 워크북의 'Buzz 1' 시트(썸트렌드 일별 언급량) → data/hatchuping/buzz_daily.csv.

    사용자가 매일 손으로 채우는 워크북이라 Excel에 열려 있을 수 있다 —
    임시 복사본에서 읽어 잠금을 피하고, 실패해도 나머지 업데이트는 계속한다."""
    import shutil
    import tempfile

    import pandas as pd
    try:
        tmp = Path(tempfile.gettempdir()) / "_buzz_trend_read_copy.xlsx"
        shutil.copy2(BUZZ_XLSX, tmp)
        raw = pd.read_excel(tmp, sheet_name="Buzz 1", header=None, usecols="C:I")
        raw.columns = ["date", "community", "instagram", "blog", "news", "youtube", "total"]
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        df = raw.dropna(subset=["date", "total"]).copy()
        df = df[pd.to_numeric(df["total"], errors="coerce").notna()]
        df["date"] = df["date"].dt.date
        df = df.sort_values("date").drop_duplicates("date", keep="last")
        for c in ["community", "instagram", "blog", "news", "youtube", "total"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        df.to_csv(DATA / "buzz_daily.csv", index=False)
        print(f"buzz_daily.csv written — {len(df)} days, {df['date'].min()} ~ {df['date'].max()}")

        # Price 시트 (B=날짜, C=SAMG엔터 419530 주가) → stock_price.csv
        pr = pd.read_excel(tmp, sheet_name="Price", header=None, usecols="B:C")
        pr.columns = ["date", "price"]
        pr["date"] = pd.to_datetime(pr["date"], errors="coerce")
        pr["price"] = pd.to_numeric(pr["price"].astype(str).str.replace(",", ""), errors="coerce")
        pr = pr.dropna().sort_values("date").drop_duplicates("date", keep="last")
        pr["date"] = pr["date"].dt.date
        pr["price"] = pr["price"].astype(int)
        pr.to_csv(DATA / "stock_price.csv", index=False)
        print(f"stock_price.csv written — {len(pr)} days, {pr['date'].min()} ~ {pr['date'].max()}")
        tmp.unlink()
    except Exception as e:  # noqa: BLE001 — 언급량은 부가 데이터, 본 업데이트를 막지 않는다
        print("buzz export skipped:", e)


def main():
    scrape = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = date.fromisoformat(scrape["date"])
    m, t = scrape["main"], scrape["teaser"]

    # 아침 수집분은 어제 마감치 (모듈 docstring의 날짜 규칙 참고)
    morning = datetime.now().hour < 12
    yt_d = d - timedelta(days=1) if morning else d
    print(f"youtube 수집 {d} {'아침' if morning else '오후'} → {yt_d} 행에 기록"
          f" ({'어제 확정' if morning else '오늘 잠정'})")

    pythoncom.CoInitialize()
    xl, wb, attached = get_excel_and_wb()
    prev_alerts, prev_screen = xl.DisplayAlerts, xl.ScreenUpdating
    xl.DisplayAlerts = False
    xl.ScreenUpdating = False
    try:
        # ---- 1. 메인 Daily
        ws = wb.Worksheets("메인 Daily")
        n, existed = find_row_by_date(ws, yt_d)
        if existed:
            print("main row for", yt_d, "already exists — overwriting it")
        ws.Cells(n, 1).Value = yt_d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (yt_d - MAIN_RELEASE).days
        for col, v in zip(range(3, 9), [m["ttv"]["views"], m["ttv"]["likes"], m["ttv"]["comments"],
                                        m["byform"]["views"], m["byform"]["likes"], m["byform"]["comments"]]):
            ws.Cells(n, col).Value = v
            ws.Cells(n, col).Font.Color = 0xFF0000  # blue (BGR) = scraped input
        ws.Cells(n, 9).Formula = f"=C{n}+F{n}"
        ws.Cells(n, 10).Formula = f"=D{n}+G{n}"
        ws.Cells(n, 11).Formula = f"=E{n}+H{n}"
        ws.Cells(n, 12).Formula = f"=I{n}-I{n-1}" if n > 5 else None
        ws.Cells(n, 13).Formula = f"=I{n}-I{n-7}" if n - 7 >= 5 else None
        if n - 7 < 5:
            ws.Cells(n, 13).Value = "-"
        ws.Cells(n, 14).Formula = f"=I{n}/'원본영상 Sources'!$G$3"
        fmt_row(ws, n, (3, 11), NUM)
        fmt_row(ws, n, (12, 13), DELTA)
        ws.Cells(n, 14).NumberFormat = PCT
        main_row = n

        # ---- 2. 티저 Daily
        ws = wb.Worksheets("티저 Daily")
        n, _ = find_row_by_date(ws, yt_d)
        ws.Cells(n, 1).Value = yt_d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (yt_d - TEASER_RELEASE).days
        for col, v in zip(range(3, 11), [t["ttv"]["views"], t["ttv"]["likes"], t["ttv"]["comments"],
                                         t["byform"]["views"], t["byform"]["likes"], t["byform"]["comments"],
                                         t["cns"]["views"], t["cns"]["likes"]]):
            ws.Cells(n, col).Value = v
            ws.Cells(n, col).Font.Color = 0xFF0000  # blue (BGR) = scraped input
        ws.Cells(n, 11).Formula = f"=C{n}+F{n}+I{n}"
        ws.Cells(n, 12).Formula = f"=E{n}+H{n}"
        ws.Cells(n, 13).Formula = f"=K{n}-K{n-1}" if n > 5 else None
        ws.Cells(n, 14).Formula = f"=K{n}-K{n-7}" if n - 7 >= 5 else None
        if n - 7 < 5:
            ws.Cells(n, 14).Value = "-"
        ws.Cells(n, 15).Formula = f"=K{n}/'원본영상 Sources'!$G$6"
        fmt_row(ws, n, (3, 12), NUM)
        fmt_row(ws, n, (13, 14), DELTA)
        ws.Cells(n, 15).NumberFormat = PCT

        # ---- 3. 댓글속도 Velocity (new main comments today)
        ws = wb.Worksheets("댓글속도 Velocity")
        n, _ = find_row_by_date(ws, yt_d)
        total_c = m["ttv"]["comments"] + m["byform"]["comments"]
        ws.Cells(n, 1).Value = yt_d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (yt_d - MAIN_RELEASE).days
        ws.Cells(n, 4).Formula = f"=D{n-1}+C{n}"
        prev_cum = ws.Cells(n - 1, 4).Value or 0
        ws.Cells(n, 3).Value = max(0, total_c - int(prev_cum))
        ws.Cells(n, 3).Font.Color = 0xFF0000
        ws.Cells(n, 5).Formula = "='원본영상 Sources'!$G$5"
        fmt_row(ws, n, (3, 5), NUM)

        # ---- 4. sentiment (optional)
        if scrape.get("sentiment"):
            s = scrape["sentiment"]
            ws = wb.Worksheets("감성 Sentiment")
            if s.get("main_m2"):
                for i, v in enumerate(s["main_m2"]):
                    ws.Cells(6 + i, 4).Value = v          # D6:D10
            if s.get("teaser_m2"):
                for i, v in enumerate(s["teaser_m2"]):
                    ws.Cells(19 + i, 4).Value = v         # D19:D23
            if s.get("note"):
                ws.Cells(14, 1).Value = s["note"]

        # ---- 5. recalc + error check + save
        xl.CalculateFull()
        errs = []
        for sname in ["요약 Summary", "메인 Daily", "티저 Daily", "댓글속도 Velocity", "감성 Sentiment"]:
            used = wb.Worksheets(sname).UsedRange
            for row in used.Rows:
                for cell in row.Cells:
                    txt = str(cell.Text)
                    if any(e in txt for e in ("#REF!", "#NAME?", "#VALUE!", "#DIV/0!")):
                        errs.append((sname, cell.Address, txt))
        if errs:
            raise RuntimeError(f"formula errors, NOT saved: {errs}")
        wb.Save()
        print("excel saved (attached to user's Excel:" , attached, ")")

        # ---- 6. export site data from the workbook
        def sheet_rows(name, ncols):
            ws = wb.Worksheets(name)
            lr = last_data_row(ws)
            out = []
            for r in range(5, lr + 1):
                row = []
                for c in range(1, ncols + 1):
                    v = ws.Cells(r, c).Value
                    if hasattr(v, "date"):
                        v = v.date().isoformat()
                    row.append(v)
                out.append(row)
            return out

        def csv_write(path, header, rows, keep):
            lines = [",".join(header)]
            for row in rows:
                vals = [row[i] for i in keep]
                lines.append(",".join("" if v is None else (str(int(v)) if isinstance(v, float) and v == int(v) else str(v)) for v in vals))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        rows = sheet_rows("메인 Daily", 11)
        csv_write(DATA / "daily_main.csv",
                  ["date", "day", "ttv_views", "ttv_likes", "ttv_comments", "byform_views",
                   "byform_likes", "byform_comments", "total_views", "total_likes", "total_comments"],
                  rows, list(range(11)))
        rows = sheet_rows("티저 Daily", 12)
        csv_write(DATA / "daily_teaser.csv",
                  ["date", "day", "ttv_views", "ttv_likes", "ttv_comments", "byform_views",
                   "byform_likes", "byform_comments", "cns_views", "cns_likes", "total_views", "total_comments"],
                  rows, list(range(12)))
        rows = sheet_rows("댓글속도 Velocity", 4)
        csv_write(DATA / "velocity.csv", ["date", "day", "new_comments", "cum_comments"], rows, [0, 1, 2, 3])

        ws = wb.Worksheets("감성 Sentiment")
        sent = json.loads((DATA / "sentiment.json").read_text(encoding="utf-8"))
        sent["as_of"] = d.isoformat()
        sent["main"]["m1"] = [int(ws.Cells(6 + i, 2).Value) for i in range(5)]
        sent["main"]["m2"] = [int(ws.Cells(6 + i, 4).Value) for i in range(5)]
        sent["teaser"]["m1"] = [int(ws.Cells(19 + i, 2).Value) for i in range(5)]
        sent["teaser"]["m2"] = [int(ws.Cells(19 + i, 4).Value) for i in range(5)]
        (DATA / "sentiment.json").write_text(json.dumps(sent, ensure_ascii=False, indent=2), encoding="utf-8")

        meta = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
                "updated_by": "daily scheduled task"}
        (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("site data files written")
    finally:
        try:
            xl.DisplayAlerts = prev_alerts
            xl.ScreenUpdating = prev_screen
        except Exception:
            pass
        if not attached:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
            try:
                xl.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    # ---- 6.5 예매율 (optional)
    if scrape.get("booking"):
        update_booking(d, scrape["booking"])

    # ---- 6.6 언급량 (썸트렌드 buzz 워크북 → buzz_daily.csv)
    export_buzz()

    # ---- 7. git push (site auto-redeploys)
    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        r = git("commit", "-m", f"hatchuping tracker daily update {d.isoformat()}")
        if r.returncode == 0:
            git("pull", "--rebase")  # GitHub Actions also commits to this repo
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
        else:
            print("git: nothing new to commit")
    else:
        print("git: repo not initialized yet — skipped")


if __name__ == "__main__":
    main()
