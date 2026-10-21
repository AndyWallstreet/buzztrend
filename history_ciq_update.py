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

수식 작성은 애드인 없는 안전 인스턴스에서 파일로 하고, 라이브 엑셀은 열어서
새로고침만 한다 (라이브 인스턴스에 수식을 대량 입력하면 애드인이 엑셀을 죽인 적
있음).
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
           ("ebitda", "IQ_TEV_EBITDA"), ("per", "IQ_PE_EXCL"), ("pbr", "IQ_PBV"),
           ("fcf", "IQ_TEV_UFCF")]
NO_PERIOD = {"IQ_PE_EXCL", "IQ_PBV"}         # SPG 에서 기간 인자 없이 날짜만 받는 지표
LAST_COL = chr(ord("C") + len(METRICS) - 1)   # 수식이 들어가는 마지막 열
TEMP_XLSX = str(OUT / "_hist_temp.xlsx")


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


def build_formula_workbook(tickers, dates):
    """애드인 없는 자동화 인스턴스에서 수식 워크북을 만들어 파일로 저장."""
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
        # 날짜는 글자(M/D/YYYY)로 — SPG 는 "LTM","8/31/2026" 형식만 받았다 ("IQ_LTM","2026-08-31" 은
        # #INVALID FUNCTION PARAMETER, 2026-10-21 확인). 열 서식을 텍스트로 먼저 바꿔 엑셀이 날짜로 바꾸지 않게.
        ws.Range(f"B2:B{n + 1}").NumberFormat = "@"
        ws.Range(f"B2:B{n + 1}").Value = tuple((f"{d.month}/{d.day}/{d.year}",)
                                                for t in tickers for d in dates)
        for ci, (name, mn) in enumerate(METRICS):
            col = chr(ord("C") + ci)
            # 2026-10-21: 예전 CIQ() 는 9/11 오피스 업데이트 뒤 등록이 안 됨(#NAME?) → Cap IQ Pro 의 SPG() 로.
            # EV 배수는 "LTM" 기간 + 날짜, PER·PBR 은 기간 인자 없이 날짜만 (LTM 을 주면 #INVALID FUNCTION PARAMETER).
            if mn in NO_PERIOD:
                ws.Range(f"{col}2:{col}{n + 1}").FormulaR1C1 = f'=SPG(RC1,"{mn}",RC2)'
            else:
                ws.Range(f"{col}2:{col}{n + 1}").FormulaR1C1 = f'=SPG(RC1,"{mn}","LTM",RC2)'
        Path(TEMP_XLSX).unlink(missing_ok=True)
        tmp.SaveAs(TEMP_XLSX, FileFormat=51)
    finally:
        tmp.Close(SaveChanges=False)
        xl.Quit()


def fill_pbr_from_histdb(df):
    """SPG 의 IQ_PBV(날짜만) 는 달에 따라 'NA' 가 많다 (SILICON2 2021~26 에서 62달 중 29달만 값, 2026-10-21).
    빈 달은 전 종목 DB(histdb: 네이버 주가 ÷ DART 장부가, TTM) 의 같은 달 PBR 로 채운다 — 근사치라 pbr_src 열에 표시."""
    hp = Path(__file__).resolve().parent / "data" / "histdb" / "multiples.csv.gz"
    df["pbr_src"] = df["pbr"].notna().map({True: "spg", False: None})
    if not hp.exists():
        return df
    h = pd.read_csv(hp)
    h["ym"] = h["date"].str[:7]
    hm = h.groupby(["ticker", "ym"])["pbr"].last()
    df["ym"] = df["date"].str[:7]
    miss = df["pbr"].isna()
    fill = pd.Series([hm.get((t, y), float("nan")) for t, y in zip(df.loc[miss, "ticker"], df.loc[miss, "ym"])],
                     index=df.index[miss], dtype="float64").round(4)
    df["pbr"] = df["pbr"].astype("float64")
    df.loc[miss, "pbr"] = fill
    df.loc[miss & df["pbr"].notna(), "pbr_src"] = "histdb"
    n = int((df["pbr_src"] == "histdb").sum())
    print(f"  PBR 빈 달 {int(miss.sum())}개 중 {n}개를 histdb 로 채움")
    return df.drop(columns=["ym"])


def attach_live():
    """자동화 전용 엑셀 인스턴스에 연결 (사용자 작업 인스턴스는 건드리지 않는다)."""
    from evfcf_update import get_work_instance
    return get_work_instance()


XLA_PATH = r"C:\Program Files\SNL Financial\SNLxl\SNLXLAddin.xla"


def ensure_snl_xla(xl):
    """CIQ 함수가 실제로 동작하는지 수식으로 검증하고, #NAME?면 XLA를
    언로드→재로드해서 재등록한다 (IsOpen=True여도 등록이 깨진 경우가 있다)."""
    NAME_ERR = -2146826259  # #NAME? 오류 코드

    def works():
        wb = xl.Workbooks.Add()
        try:
            ws = wb.Worksheets(1)
            ws.Range("A1").Formula = '=SPG("A005930","IQ_TEV_TOTAL_REV","LTM")'   # Cap IQ Pro 함수로 검사
            ws.Range("A1").Calculate()
            time.sleep(1)
            v = retry(lambda: ws.Range("A1").Value, tries=10, wait=2, label="test read")
        finally:
            wb.Close(SaveChanges=False)
        # #PEND(문자열)나 숫자면 함수 등록 OK, #NAME?(오류 코드)면 깨진 상태
        return v != NAME_ERR

    if works():
        print("CIQ 함수 정상")
        return
    print("CIQ 함수 #NAME? — XLA 재등록 시도")
    for a in xl.AddIns:
        if a.Name == "SNLXLAddin.xla":
            try:
                a.Installed = False
            except Exception:
                pass
    time.sleep(2)
    try:
        xl.Workbooks.Open(XLA_PATH)
    except Exception as e:
        print("XLA 열기 실패:", repr(e)[:80])
    for a in xl.AddIns:
        if a.Name == "SNLXLAddin.xla":
            try:
                a.Installed = True
            except Exception:
                pass
    if not works():
        raise RuntimeError("CIQ 함수 등록 실패 — 엑셀을 완전히 종료 후 다시 시도하세요")
    print("XLA 재등록 성공")


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
    print(f"1) 수식 워크북 작성 ({n}행 × {len(METRICS)}지표, 안전 인스턴스)...")
    build_formula_workbook(tickers, dates)

    print("2) 라이브 엑셀에서 새로고침...")
    xl = attach_live()
    ensure_snl_xla(xl)
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
                vals = ws.Range(f"C2:{LAST_COL}{n + 1}").Value
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

        vals = retry(lambda: ws.Range(f"C2:{LAST_COL}{n + 1}").Value, label="extract")
        rows = []
        i = 0
        for t in tickers:
            for d in dates:
                rec = {"ticker": t, "date": d.isoformat()}
                for (name, mn), v in zip(METRICS, vals[i]):
                    if isinstance(v, float) and mn == "IQ_PBV":
                        v = v / 100.0      # SPG 의 IQ_PBV 는 ×100 (162.2 = PBR 1.62) — 2026-10-21 histdb 와 대조 확인
                    rec[name] = round(v, 4) if isinstance(v, float) else None
                rows.append(rec)
                i += 1
        df = pd.DataFrame(rows)
        df = fill_pbr_from_histdb(df)
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
             "freq": "monthly", "basis": "LTM (Cap IQ Pro SPG)"}, ensure_ascii=False, indent=1),
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
