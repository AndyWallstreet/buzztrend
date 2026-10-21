# -*- coding: utf-8 -*-
"""밸류 스크리너 '현재 멀티플' 갱신 — 비교기업 워크북(v05)의 CapIQ 수식을 새로고침해 사본으로 뽑는다.

Usage:
    python screener_refresh.py            # 새로고침 → 사본 저장 → screener_update.py 사본 → 끝
    (끝나면: git add data/screener && git commit && git push)

왜 (PM 2026-10-21): 사이트의 현재 멀티플이 2026-08-21(v05 저장 시점)에 멈춰 있었다. 원본 워크북은
절대 저장하지 않는다 — 읽기 전용으로 열어 새로고침한 뒤 SaveCopyAs 로 사본만 만든다.

절차 (capiq-refresh-via-com 메모의 검증된 방법):
  1. 작업용 엑셀 인스턴스(excel.exe /x) — PM 이 쓰는 엑셀에는 절대 붙지 않는다 (evfcf_update.get_work_instance)
  2. SNLXLAddin.xla 를 워크북 열기 '전에' 로드 (안 하면 CIQ 수식이 #NAME? 로 굳음)
  3. 워크북 읽기 전용으로 열기 (OneDrive 동기화 파일을 편집 모드로 열면 Rtc.dll 크래시 이력)
  4. Data 시트 활성화 → xl.Run("RefreshSheet")  (RefreshWorkbook 보다 안전, 활성 시트의 #PEND 만 채움)
  5. 스크린 블록(CW:EB)에 #PEND/#REFRESH 가 없어질 때까지 폴링 (최대 40분)
  6. SaveCopyAs 임시 사본 → screener_update.py <사본> → 사본 삭제
"""
import subprocess
import sys
import time
from pathlib import Path

import win32com.client
from pywintypes import com_error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evfcf_update import get_work_instance  # noqa: E402

XLSX = (r"C:\Users\user99i1\LK자산운용\운용본부 - 문서\Resources"
        r"\02_Industry Analysis\Comparables cap iq_value_AJ editing_v05.xlsx")
XLA = r"C:\Program Files\SNL Financial\SNLxl\SNLXLAddin.xla"
COPY = Path(__file__).resolve().parent / "data" / "screener" / "_v05_refreshed_copy.xlsx"
FIRST, LAST = 9, 2901            # Data 시트 스크린 블록 행 범위
BLOCK = f"CW{FIRST}:EB{LAST}"    # CW:DJ 스크린 + DY:EB 2026E 원본
PY = sys.executable


def retry(fn, tries=80, wait=3, label=""):
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:          # 0x800AC472 = 엑셀이 바쁨 → 기다렸다 다시
            last = e
            time.sleep(wait)
    raise RuntimeError(f"Excel이 계속 바쁩니다: {label}: {last}")


def count_pending(ws):
    vals = ws.Range(BLOCK).Value
    pend = sum(1 for row in vals for v in row if v in ("#PEND", "#REFRESH"))
    name_err = sum(1 for row in vals for v in row if v == -2146826259)   # #NAME?
    return pend, name_err


def main():
    print("작업용 엑셀 인스턴스 연결...", flush=True)
    xl = get_work_instance()
    for a in xl.AddIns:
        if a.Name == "SNLXLAddin.xla" and not a.IsOpen:
            xl.Workbooks.Open(XLA)
            print("SNL XLA 강제 로드", flush=True)
    xl.DisplayAlerts = False

    print("워크북 읽기 전용으로 열기 (40MB, 1~2분)...", flush=True)
    wb = retry(lambda: xl.Workbooks.Open(XLSX, UpdateLinks=0, ReadOnly=True), label="open")
    try:
        ws = wb.Worksheets("Data")
        retry(lambda: ws.Activate(), label="activate")
        p0, n0 = retry(lambda: count_pending(ws), label="count0")
        print(f"새로고침 전: #PEND {p0:,} · #NAME? {n0:,}", flush=True)
        retry(lambda: xl.Run("RefreshSheet"), label="RefreshSheet")
        deadline = time.time() + 2400
        pend = -1
        while time.time() < deadline:
            time.sleep(20)
            try:
                pend, nerr = count_pending(ws)
            except com_error:
                continue
            print(f"  남은 #PEND {pend:,} · #NAME? {nerr:,}", flush=True)
            if pend == 0:
                break
        if pend != 0:
            raise RuntimeError(f"새로고침 미완료 (#PEND {pend}) — 다시 실행하세요")
        if nerr:
            print(f"⚠ #NAME? {nerr:,}개 — XLA 미로드 상태로 계산된 셀. 사본은 만들되 결과를 의심할 것", flush=True)
        COPY.unlink(missing_ok=True)
        retry(lambda: wb.SaveCopyAs(str(COPY)), label="SaveCopyAs")
        print(f"사본 저장: {COPY.name}", flush=True)
    finally:
        try:
            wb.Close(SaveChanges=False)          # 원본은 절대 저장하지 않음
        except Exception:
            pass

    print("screener_update.py 실행...", flush=True)
    r = subprocess.run([PY, str(Path(__file__).resolve().parent / "screener_update.py"), str(COPY)],
                       cwd=str(Path(__file__).resolve().parent))
    COPY.unlink(missing_ok=True)
    if r.returncode:
        raise SystemExit(f"screener_update.py 실패 (exit {r.returncode})")
    print("완료 — git add data/screener && git commit && git push", flush=True)


if __name__ == "__main__":
    main()
