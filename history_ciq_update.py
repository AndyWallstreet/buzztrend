# -*- coding: utf-8 -*-
"""관심종목의 과거 멀티플(월별, LTM)을 Capital IQ에서 뽑아 사이트 데이터로 저장.

Usage:
    python history_ciq_update.py [추가티커 ...]     # 예: python history_ciq_update.py A035420
    (끝나면: git add data/screener/history_ciq && git commit && git push)

전제: 엑셀이 열려 있고 Cap IQ Pro 애드인이 로그인돼 있어야 한다 (아무 워크북이나
열려 있으면 됨). 종목 목록은 data/screener/history_ciq/watchlist.txt — 한 줄에
하나(A123456), 자유롭게 추가.

동작: 새 임시 워크북에 종목×월(10년, 121개) CIQ 수식을 깔고 그 워크북만
새로고침(RefreshWorkbook은 활성 워크북 대상) → 값 추출 → 임시 워크북은 저장 없이
닫는다. 비교기업 워크북은 건드리지 않는다.
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd
import win32com.client
from pywintypes import com_error

OUT = Path(__file__).resolve().parent / "data" / "screener" / "history_ciq"
WATCHLIST = OUT / "watchlist.txt"
SEEDS = ["A257720", "A086450", "A419530", "A092730", "A161890", "A122870"]
MONTHS = 121  # 10년 월별 + 이번 달
METRICS = [("evs", "IQ_TEV_TOTAL_REV"), ("eve", "IQ_TEV_EBIT"),
           ("ebitda", "IQ_TEV_EBITDA"), ("per", "IQ_PE_EXCL"), ("pbr", "IQ_PBV")]


def retry(fn, tries=60, wait=3, label=""):
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise RuntimeError(f"Excel이 계속 바쁩니다: {label}: {last}")


def month_ends():
    today = dt.date.today()
    out = []
    d = today.replace(day=1)
    for _ in range(MONTHS - 1):
        d = (d - dt.timedelta(days=1)).replace(day=1)
        last_day = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        out.append(last_day)
    out.reverse()
    out.append(today)
    return out


TEMP_XLSX = str(Path(__file__).resolve().parent / "data" / "screener"
                / "history_ciq" / "_hist_temp.xlsx")


def build_formula_workbook(tickers, dates):
    """애드인 없는 자동화 인스턴스에서 수식 워크북을 만들어 파일로 저장.
    (라이브 인스턴스에 수식을 대량 입력하면 CapIQ 애드인이 엑셀을 죽이는
    일이 있어서, 어제 검증된 '작성은 안전 인스턴스, 새로고침은 라이브' 경로)"""
    n = len(tickers) * len(dates)
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    tmp = xl.Workbooks.Add()
    xl.Calculation = -4135  # manual
    xl.CalculateBeforeSave = False
    try:
        ws = tmp.Worksheets(1)
        tick_col, date_col = [], []
        for t in tickers:
            for d in dates:
                tick_col.append((t,))
                date_col.append((d.strftime("%Y-%m-%d"),))
        ws.Range(f"A2:A{n + 1}").Value = tuple(tick_col)
        ws.Range(f"B2:B{n + 1}").Value = tuple(date_col)
        for ci, (name, mn) in enumerate(METRICS):
            col = chr(ord("C") + ci)
            ws.Range(f"{col}2:{col}{n + 1}").FormulaR1C1 = f'=CIQ(RC1,"{mn}","IQ_LTM",RC2)'
        Path(TEMP_XLSX).unlink(missing_ok=True)
        tmp.SaveAs(TEMP_XLSX, FileFormat=51)
    finally:
        tmp.Close(SaveChanges=False)
        xl.Quit()


def attach_live():
    """애드인이 로드된 라이브 엑셀에 연결.
    없으면 임시 파일을 셸로 열어 인스턴스를 만든다 (빈 엑셀은 시작 화면 상태라
    COM ROT에 등록되지 않아 붙을 수 없다)."""
    try:
        return win32com.client.GetActiveObject("Excel.Application")
    except Exception:
        pass
    import os
    os.startfile(TEMP_XLSX)
    time.sleep(25)
    return retry(lambda: win32com.client.GetActiveObject("Excel.Application"),
                 tries=15, wait=4, label="엑셀 연결 — 엑셀을 직접 한 번 열어주세요")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not WATCHLIST.exists():
        WATCHLIST.write_text("\n".join(SEEDS), encoding="utf-8")
    tickers = [t.strip().upper() for t in WATCHLIST.read_text(encoding="utf-8").split()
               if t.strip()]
    for extra in sys.argv[1:]:
        t = extra.strip().upper()
        if t not in tickers:
            tickers.append(t)
    WATCHLIST.write_text("\n".join(tickers), encoding="utf-8")
    print(f"관심종목 {len(tickers)}개: {', '.join(tickers)}")

    dates = month_ends()
    n = len(tickers) * len(dates)
    print(f"1) 수식 워크북 작성 ({n}행 × 5지표, 안전 인스턴스)...")
    build_formula_workbook(tickers, dates)

    print("2) 라이브 엑셀에서 새로고침...")
    xl = attach_live()
    wb = next((w for w in xl.Workbooks if w.Name == Path(TEMP_XLSX).name), None)
    if wb is None:
        wb = retry(lambda: xl.Workbooks.Open(TEMP_XLSX), label="임시 워크북 열기")
    try:
        ws = wb.Worksheets(1)
        retry(lambda: ws.Activate(), label="activate")
        retry(lambda: xl.Run("RefreshWorkbook"), label="refresh")
        print("CapIQ 새로고침 중...")

        deadline = time.time() + 1800
        unresolved = -1
        while time.time() < deadline:
            try:
                vals = ws.Range(f"C2:G{n + 1}").Value
                unresolved = sum(1 for row in vals for v in row
                                 if v in ("#PEND", "#REFRESH"))
                if unresolved == 0:
                    break
                print(f"  남은 셀: {unresolved}", flush=True)
            except com_error:
                pass
            time.sleep(15)
        if unresolved != 0:
            raise RuntimeError(f"새로고침 미완료 (남은 셀 {unresolved}) — 나중에 다시 실행하세요")

        vals = retry(lambda: ws.Range(f"C2:G{n + 1}").Value, label="extract")
        rows = []
        i = 0
        for t in tickers:
            for d in dates:
                rec = {"ticker": t, "date": d.isoformat()}
                for (name, _), v in zip(METRICS, vals[i]):
                    rec[name] = round(v, 4) if isinstance(v, float) else None
                rows.append(rec)
                i += 1
        df = pd.DataFrame(rows)
        written = []
        for t in tickers:
            sub = df[df.ticker == t].drop(columns=["ticker"])
            if sub[[m for m, _ in METRICS]].notna().any().any():
                sub.to_csv(OUT / f"{t}.csv", index=False)
                written.append(t)
            else:
                print(f"  {t}: CIQ 데이터 없음 — 건너뜀")
        (OUT / "meta.json").write_text(json.dumps(
            {"as_of": dt.date.today().isoformat(), "tickers": written,
             "freq": "monthly", "basis": "LTM (CIQ)"}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"OK — {len(written)}개 종목 저장: {OUT}")
        print("이제: git add data/screener/history_ciq && git commit -m 'ciq history' && git push")
    finally:
        try:
            wb.Close(SaveChanges=False)
        except Exception:
            pass
        Path(TEMP_XLSX).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
