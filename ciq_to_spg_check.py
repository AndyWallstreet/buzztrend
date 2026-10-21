# -*- coding: utf-8 -*-
"""v06 (SPG 변환본) 검증.
1) 작업용 엑셀(/x)에서 열어 복구 창 없이 열리는지, 시트 12개, 수식이 파싱되는지 확인 (저장 안 함).
2) 변환된 Data 행 9~N 의 핵심 열 수식을 스크래치 워크북에 복사해 실제 값을 받고 기준값과 비교.
   기준값 = 사이트 스크리너 csv (screener_spg_update.py 가 같은 날 SPG 로 받은 값) → 날짜를 그 as_of 로 맞춰 비교.
   (v05 캐시값은 저장일(08-21)보다 이른 시점에 새로고침된 것이라 LTM 창이 달라 정확 비교가 안 됨 — 2026-10-21 확인)
Usage: python ciq_to_spg_check.py <v06.xlsx> <screener_data.csv> [n_rows] [--values-only] [--date 46316]
"""
import csv
import html
import re
import sys
import time
import zipfile

sys.path.insert(0, r"C:\Users\user99i1\buzztrend")
import evfcf_update as e  # noqa: E402

COLS = ["H", "P", "BB", "BC", "BE", "BH", "BN", "BO", "BT", "CF", "CG", "CI", "CK", "CM", "CL", "DY", "DZ", "EA", "EB"]
# 변환 수식 열 ↔ 스크리너 csv 열 (둘 다 같은 날 SPG 값이면 거의 같아야 함)
VS = {"CK": ("ev_sales", "LTM"), "CM": ("ev_ebit", "LTM"), "BB": ("ev_ebitda", "LTM"), "BH": ("per", "LTM"),
      "BN": ("pbr", None), "DY": ("ev_sales", "2026E"), "DZ": ("ev_ebit", "2026E"), "EA": ("ev_ebitda", "2026E"),
      "EB": ("per", "2026E"), "BE": ("roic", None)}
NAMES = {"IQ_FY- 2": "998", "IQ_FY- 1": "999", "IQ_FY-2": "998", "IQ_FY-1": "999", "IQ_FY": "1000",
         "IQ_FQ": "500", "IQ_LTM": "2000", "IQ_CY": "10000"}


def sheet_formulas(path, sheet_xml, rows):
    z = zipfile.ZipFile(path)
    x = z.read(sheet_xml).decode("utf8")
    out, tick = {}, {}
    # 빈 셀은 <c .../> 자기닫힘 — 이걸 처리하지 않으면 뒤 셀 내용이 앞 열로 붙는다 (2026-10-21 버그)
    for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', x, re.S):
        c, r = m.group(1), int(m.group(2))
        body = m.group(4) or ""
        if r not in rows:
            continue
        if c in COLS:
            fm = re.search(r"<f[^>]*>([^<]*)</f>", body)
            if fm:
                out[(c, r)] = html.unescape(fm.group(1))
        if c == "B":
            v = re.search(r"<v>([^<]*)</v>", body)
            if v:
                tick[r] = v.group(1)
    return out, tick


def localize(f, r, ticker, date):
    f = f.replace("_xll.SNL.Clients.Office.Excel.Functions.", "").replace("_xlfn.", "").replace("_xlpm.", "")
    f = f.replace(f"$B{r}", f'"{ticker}"').replace("$J$4", str(date))
    f = f.replace("$C$2923", '"Basic"').replace("$A$2929", '"Basic"').replace("$A$2930", '"Diluted Exercisable"')
    for k, v in NAMES.items():
        f = f.replace(k, v)
    return "=" + f


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main(v06, ref_csv, n=25, date=46316):
    rows = range(9, 9 + n)
    forms, tick = sheet_formulas(v06, "xl/worksheets/sheet5.xml", set(rows))
    xl = e.get_work_instance()
    xl.DisplayAlerts = False
    if "--values-only" not in sys.argv:
        wb = xl.Workbooks.Open(v06, UpdateLinks=0, ReadOnly=True)
        xl.Calculation = -4135
        print("열림:", wb.Name, "| 시트", wb.Worksheets.Count, [s.Name for s in wb.Worksheets])
        ws = wb.Worksheets("Data")
        for ref in ("H9", "BE9", "BN9", "C2920"):
            print("  Data!" + ref, "→", ws.Range(ref).Formula[:120])
        print("  Mult History!D13 →", wb.Worksheets("Mult History").Range("D13").Formula[:160])
        wb.Close(SaveChanges=False)
    wb = xl.Workbooks.Add(); ws = wb.Worksheets(1)
    xl.Calculation = -4135  # 워크북이 하나는 열려 있어야 설정 가능
    ws.Cells(1, 1).Value = "row"; ws.Cells(1, 2).Value = "ticker"
    for j, c in enumerate(COLS, start=3):
        ws.Cells(1, j).Value = c
    for i, r in enumerate(rows, start=2):
        ws.Cells(i, 1).Value = r; ws.Cells(i, 2).Value = tick.get(r)
        for j, c in enumerate(COLS, start=3):
            f = forms.get((c, r))
            if f:
                ws.Cells(i, j).Formula = localize(f, r, tick.get(r), date)
    xl.Calculate()
    nr, nc = len(rows) + 1, len(COLS) + 2

    def snap():
        return ws.Range(ws.Cells(1, 1), ws.Cells(nr, nc)).Value

    def pending(v):
        return sum(1 for row in v[1:] for x in row[2:] if x is None or (isinstance(x, str) and x.strip() in ("#PEND", "#REFRESH", "")))

    time.sleep(10)
    try:
        xl.Run("RefreshWorkbook")  # 한 번만 — 반복 호출하면 새로고침이 처음부터 다시 돌아 끝나지 않음 (2026-10-21)
    except Exception as ex:
        print("refresh err", ex)
    t0 = time.time(); last = None
    while time.time() - t0 < 900:
        v = snap(); p = pending(v)
        if p != last:
            print(f"  {time.time()-t0:4.0f}s 미수신 {p}")
            last = p
        if p == 0:
            break
        time.sleep(15)
    print(f"값 수신 {time.time()-t0:.0f}s, 미수신 {p}")
    ref = {r["ticker"]: r for r in csv.DictReader(open(ref_csv, encoding="utf-8-sig"))}
    v = snap()
    print(f"\n기준: {ref_csv} (as-of 날짜 {date})")
    print(f"{'col':4s} {'csv col':10s} {'n':>3s} {'both':>5s} {'<1%':>5s} {'<5%':>5s}  examples(new | csv)")
    for j, c in enumerate(COLS, start=2):
        pairs = []
        for row in v[1:]:
            t = row[1]; new = row[j]; rr = ref.get(t, {})
            if c in VS:
                col, src = VS[c]
                o = rr.get(col)
                if src and rr.get(col + "_src", "") != src:
                    o = None  # 같은 기준(LTM/2026E)끼리만
            else:
                o = None
            pairs.append((new, o))
        both = [(a, num(b)) for a, b in pairs if isinstance(a, (int, float)) and num(b) is not None]
        w1 = sum(1 for a, b in both if abs(a - b) <= 0.01 * max(abs(b), 1e-9))
        w5 = sum(1 for a, b in both if abs(a - b) <= 0.05 * max(abs(b), 1e-9))
        got = sum(1 for a, _ in pairs if a is not None)
        ex = "; ".join(f"{(round(a,3) if isinstance(a,float) else a)}|{(round(num(b),3) if num(b) is not None else b)}" for a, b in pairs[:3])
        print(f"{c:4s} {VS.get(c, ('-',))[0]:10s} {got:3d} {len(both):5d} {w1:5d} {w5:5d}  {ex}")
    wb.Saved = True


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    date = int(sys.argv[sys.argv.index("--date") + 1]) if "--date" in sys.argv else 46316
    main(args[0], args[1], int(args[2]) if len(args) > 2 else 25, date)
