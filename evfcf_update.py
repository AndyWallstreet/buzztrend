# -*- coding: utf-8 -*-
"""전 종목 EV/FCF (LTM)를 Capital IQ에서 뽑아 비교기업 워크북 EC열에 채운다.

Usage:
    python evfcf_update.py
    (끝나면 screener_update.py를 다시 돌려 사이트 데이터에 반영)

FCF 멀티플은 forward 컨센서스가 거의 없어 LTM만 쓴다. 큰 워크북 전체 새로고침은
애드인이 자주 죽어서, 임시 워크북에서 EV/FCF만 뽑아 '값'으로 붙여넣는다.
(EC열은 수식이 아니라 값 — 갱신하려면 이 스크립트를 다시 실행)
"""
import time
from pathlib import Path

import pandas as pd
import win32com.client
from pywintypes import com_error

V04 = (r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Resources"
       r"\02_Industry Analysis\Comparables cap iq_value_AJ editing_v04.xlsx")
CSV = Path(__file__).resolve().parent / "data" / "screener" / "screener_data.csv"
TEMP = str(Path(__file__).resolve().parent / "data" / "screener" / "_evfcf_temp.xlsx")
# 후보 ratio mnemonic + 구성요소 백업 (TEV bn, 영업현금흐름 mm, CAPEX mm)
CANDIDATES = ["IQ_TEV_UFCF", "IQ_TEV_LFCF", "IQ_TEV_FCF"]
COMPONENTS = [("TEV", '=SPG(RC1,"IQ_TEV")'),
              ("CFO", '=CIQ(RC1,"IQ_CASH_OPER","IQ_LTM")'),
              ("CAPEX", '=CIQ(RC1,"IQ_CAPEX","IQ_LTM")')]


def retry(fn, tries=60, wait=3, label=""):
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise RuntimeError(f"Excel이 계속 바쁩니다: {label}: {last}")


def get_work_instance():
    """사용자가 쓰는 인스턴스 말고, 자동화 전용 엑셀 인스턴스를 찾거나 새로 띄운다.
    (사용자 세션에서 CIQ 함수 등록이 깨져 있거나, 작업 중 크래시로 사용자 작업을
    잃을 위험이 있어 분리한다. 새 인스턴스는 정상 실행이라 애드인이 로드된다.)"""
    import subprocess
    import xlwings as xw

    def find():
        for pid in list(xw.apps.keys()):
            try:
                app = xw.apps[pid]
                names = [b.name for b in app.books]
            except Exception:
                continue
            # 사용자 작업물(매크로 워크북 등)이 없는 인스턴스만 사용
            if not any(n.lower().endswith((".xlsm", ".xlsb")) for n in names):
                return app.api
        return None

    xl = find()
    if xl is None:
        subprocess.Popen(["cmd", "/c", "start", "", "excel.exe", "/x"], shell=False)
        time.sleep(20)
        xl = retry(find, tries=10, wait=5, label="새 엑셀 인스턴스")
        if xl is None:
            raise RuntimeError("작업용 엑셀 인스턴스를 만들지 못했습니다")
    return xl


def build_temp(tickers):
    n = len(tickers)
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    tmp = xl.Workbooks.Add()
    xl.Calculation = -4135
    xl.CalculateBeforeSave = False
    try:
        ws = tmp.Worksheets(1)
        ws.Range(f"A2:A{n + 1}").Value = tuple((t,) for t in tickers)
        formulas = [f'=CIQ(RC1,"{mn}","IQ_LTM")' for mn in CANDIDATES] \
            + [f for _, f in COMPONENTS]
        for ci, f in enumerate(formulas):
            col = chr(ord("B") + ci)
            ws.Range(f"{col}2:{col}{n + 1}").FormulaR1C1 = f
        Path(TEMP).unlink(missing_ok=True)
        tmp.SaveAs(TEMP, FileFormat=51)
    finally:
        tmp.Close(SaveChanges=False)
        xl.Quit()


def main():
    tickers = pd.read_csv(CSV)["ticker"].drop_duplicates().tolist()
    n = len(tickers)
    print(f"종목 {n}개 × 후보 {len(CANDIDATES)}개 수식 작성...")
    build_temp(tickers)

    print("작업용 엑셀 인스턴스 연결...")
    xl = get_work_instance()
    # CIQ 함수 제공 XLA는 임시 워크북을 '열기 전에' 로드해야 #NAME?로 굳지 않는다
    for a in xl.AddIns:
        if a.Name == "SNLXLAddin.xla" and not a.IsOpen:
            try:
                xl.Workbooks.Open(r"C:\Program Files\SNL Financial\SNLxl\SNLXLAddin.xla")
                print("SNL XLA 강제 로드")
            except Exception as e:
                print("XLA 로드 실패:", repr(e)[:80])

    wb = next((w for w in xl.Workbooks if w.Name == Path(TEMP).name), None)
    if wb is None:
        wb = retry(lambda: xl.Workbooks.Open(TEMP), label="임시 워크북 열기")
    ncol = len(CANDIDATES) + len(COMPONENTS)
    last_col = chr(ord("B") + ncol - 1)
    try:
        ws = wb.Worksheets(1)
        retry(lambda: ws.Activate(), label="activate")
        # XLA 로드 전에 계산돼 #NAME?로 굳었을 수 있으니 강제 재계산 후 새로고침
        retry(lambda: ws.Range(f"B2:{last_col}{n + 1}").Calculate(), label="recalc")
        retry(lambda: xl.Run("RefreshWorkbook"), label="refresh")
        deadline = time.time() + 1500
        unresolved = -1
        while time.time() < deadline:
            try:
                vals = ws.Range(f"B2:{last_col}{n + 1}").Value
                unresolved = sum(1 for row in vals for v in row
                                 if v in ("#PEND", "#REFRESH"))
                if unresolved == 0:
                    break
                print(f"  남은 셀: {unresolved}", flush=True)
            except com_error:
                pass
            time.sleep(15)
        if unresolved != 0:
            raise RuntimeError(f"새로고침 미완료 ({unresolved}) — 다시 실행하세요")
        vals = retry(lambda: ws.Range(f"B2:{last_col}{n + 1}").Value, label="extract")
    finally:
        try:
            wb.Close(SaveChanges=False)
        except Exception:
            pass
        Path(TEMP).unlink(missing_ok=True)

    print("샘플 (앞 3종목):")
    for t, row in list(zip(tickers, vals))[:3]:
        print("  ", t, [str(v)[:14] for v in row])
    counts = [sum(1 for row in vals if isinstance(row[i], float))
              for i in range(len(CANDIDATES))]
    print("후보별 값 개수:", dict(zip(CANDIDATES, counts)))
    best = counts.index(max(counts))
    if counts[best] > 100:
        print("→ ratio mnemonic 사용:", CANDIDATES[best])
        fcf = {t: (row[best] if isinstance(row[best], float) else None)
               for t, row in zip(tickers, vals)}
    else:
        # ratio가 안 나오면 구성요소로 직접 계산: EV/FCF = TEV(bn)×1000 / (CFO − |CAPEX|)
        print("→ ratio 실패, 구성요소(TEV/CFO/CAPEX)로 계산")
        i0 = len(CANDIDATES)
        fcf = {}
        n_ok = 0
        for t, row in zip(tickers, vals):
            tev, cfo, capex = row[i0], row[i0 + 1], row[i0 + 2]
            if all(isinstance(v, float) for v in (tev, cfo, capex)):
                f = cfo - abs(capex)
                if f > 0:
                    fcf[t] = tev * 1000 / f
                    n_ok += 1
                else:
                    fcf[t] = None   # FCF 적자 — 멀티플 의미 없음
            else:
                fcf[t] = None
        print(f"   계산된 종목: {n_ok}개")
        if n_ok < 100:
            raise RuntimeError("구성요소 계산도 실패 — mnemonic 확인 필요")

    print("비교기업 워크북 EC열에 값 기록...")
    wb2 = next((w for w in xl.Workbooks if "Comparables cap iq_value" in w.Name), None)
    opened_here = wb2 is None
    if wb2 is None:
        wb2 = retry(lambda: xl.Workbooks.Open(V04), tries=30, wait=5, label="v04 열기")
    if wb2.ReadOnly:
        raise RuntimeError("워크북이 읽기 전용입니다 — 다른 곳에서 열려 있는지 확인")
    data = wb2.Worksheets("Data")
    retry(lambda: setattr(data.Range("EC8"), "Value",
                          f"EV/FCF (LTM · 값붙여넣기 {time.strftime('%Y-%m-%d')})"),
          label="EC8")
    cw = retry(lambda: data.Range("CW9:CW2901").Value, label="tickers")
    out = tuple((fcf.get(r[0]),) if r[0] else (None,) for r in cw)
    retry(lambda: setattr(data.Range("EC9:EC2901"), "Value", out), label="EC write")
    retry(lambda: wb2.Save(), tries=90, wait=4, label="save")
    print("워크북 저장 완료")
    copy = str(Path(__file__).resolve().parent / "data" / "screener" / "_v04_copy.xlsx")
    retry(lambda: wb2.SaveCopyAs(copy), tries=30, wait=4, label="savecopy")
    if opened_here:
        wb2.Close(SaveChanges=False)
    print(f"사본: {copy}")
    print("이제: python screener_update.py \"" + copy + "\"")


if __name__ == "__main__":
    main()
