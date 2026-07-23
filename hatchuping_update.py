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

What it does, in order:
 1. Appends one row each to '메인 Daily' / '티저 Daily' / '댓글속도 Velocity'
    in Hatchuping2 tracker_v1.xlsx via Excel COM.
    - If the user has the file open in Excel, it edits THAT open workbook
      (never quits their Excel, never touches their other workbooks).
    - Skips (idempotent) if today's date is already the last row.
 2. Updates 2편 sentiment counts if provided.
 3. Recalculates, checks for formula errors, saves.
 4. Rewrites the website data files (data/*.csv, *.json) from the workbook.
 5. git add/commit/push (skips quietly if nothing changed or no remote).
"""
import json
import subprocess
import sys
from datetime import date, datetime
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
TRACKER_NAME = "Hatchuping2 tracker_v1.xlsx"
FORECAST = r"C:\Users\user99i1\hatchuping\하츄핑2_흥행예측.xlsx"
FORECAST_NAME = "하츄핑2_흥행예측.xlsx"
REPO = Path(__file__).parent            # the buzztrend repo
DATA = REPO / "data" / "hatchuping"     # site data for pages/1_🐳_하츄핑2_예고편.py
MAIN_RELEASE = date(2026, 7, 9)
TEASER_RELEASE = date(2026, 6, 15)

NUM = "#,##0"
DELTA = "+#,##0;-#,##0;0"
PCT = "0.0%"


def get_excel_and_wb(path=TRACKER, name=TRACKER_NAME):
    """Attach to the user's open Excel if the workbook is open there; else own instance."""
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


def fmt_row(ws, r, cols, fmt):
    ws.Range(ws.Cells(r, cols[0]), ws.Cells(r, cols[1])).NumberFormat = fmt


def update_booking(d, booking):
    """Append/refresh today's row in 하츄핑2_흥행예측.xlsx '추적' sheet and booking.csv.

    booking = {"tickets": 10963, "rate": 1.5, "rank": 6}  (KOBIS 실시간 예매율)
    """
    pythoncom.CoInitialize()  # main()'s COM session may already be closed by now
    xl, wb, attached = get_excel_and_wb(FORECAST, FORECAST_NAME)
    prev_alerts, prev_screen = xl.DisplayAlerts, xl.ScreenUpdating
    xl.DisplayAlerts = False
    xl.ScreenUpdating = False
    try:
        ws = wb.Worksheets("추적")
        lr = last_data_row(ws)
        n = lr if (ws.Cells(lr, 1).Value is not None and ws.Cells(lr, 1).Value.date() == d) else lr + 1
        ws.Cells(n, 1).Value = d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        if not str(ws.Cells(n, 2).Formula).startswith("=IF"):
            ws.Cells(n, 2).Formula = f'=IF(A{n}="","","D-"&TEXT($B$2-A{n},"0"))'
        ws.Cells(n, 3).Value = booking["tickets"]
        ws.Cells(n, 3).NumberFormat = NUM
        ws.Cells(n, 4).Value = f"자동 수집 · 예매율 {booking.get('rate', '?')}% · {booking.get('rank', '?')}위"
        for col in (1, 3, 4):
            ws.Cells(n, col).Font.Color = 0xFF0000  # blue (BGR) = input
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

    # booking.csv — one row per date, newest value wins
    open_d = date(2026, 8, 5)
    path = DATA / "booking.csv"
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    header, rows = lines[0], [l for l in lines[1:] if l and not l.startswith(d.isoformat())]
    rows.append(f"{d.isoformat()},{(open_d - d).days},{booking['tickets']},{booking.get('rate', '')},{booking.get('rank', '')}")
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print("booking.csv updated")


def main():
    scrape = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = date.fromisoformat(scrape["date"])
    m, t = scrape["main"], scrape["teaser"]

    pythoncom.CoInitialize()
    xl, wb, attached = get_excel_and_wb()
    prev_alerts, prev_screen = xl.DisplayAlerts, xl.ScreenUpdating
    xl.DisplayAlerts = False
    xl.ScreenUpdating = False
    try:
        # ---- 1. 메인 Daily
        ws = wb.Worksheets("메인 Daily")
        lr = last_data_row(ws)
        if ws.Cells(lr, 1).Value is not None and ws.Cells(lr, 1).Value.date() == d:
            print("main row for", d, "already exists — overwriting it")
            n = lr
        else:
            n = lr + 1
        ws.Cells(n, 1).Value = d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (d - MAIN_RELEASE).days
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
        lr = last_data_row(ws)
        n = lr if (ws.Cells(lr, 1).Value is not None and ws.Cells(lr, 1).Value.date() == d) else lr + 1
        ws.Cells(n, 1).Value = d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (d - TEASER_RELEASE).days
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
        lr = last_data_row(ws)
        n = lr if (ws.Cells(lr, 1).Value is not None and ws.Cells(lr, 1).Value.date() == d) else lr + 1
        total_c = m["ttv"]["comments"] + m["byform"]["comments"]
        ws.Cells(n, 1).Value = d.isoformat()
        ws.Cells(n, 1).NumberFormat = "yyyy-mm-dd"
        ws.Cells(n, 2).Value = (d - MAIN_RELEASE).days
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
