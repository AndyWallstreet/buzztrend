# -*- coding: utf-8 -*-
"""YG플러스 워크북에 '앨범유통 단가' 시트 만들기 (Excel COM, 새 버전 파일로 저장).

Usage:  python ygplus_album_sheet.py [v03]
입력:   data/ygplus/quarterly.csv (ygplus_album_update.py 산출)
색:     파랑 = 하드코딩(Circle 원본) · 검정 = 계산 · 초록 = 다른 시트 참조 · 보라 = 같은 시트 참조
서식:   Arial 8pt(제목 10pt), 병합 없음.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DIR = Path(r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\band chart\기업분석 by 클로드_추후 반영")
SRC = DIR / "YG플러스_Analysis template_2026 09_v02.xlsx"
SEG = "3. 매출 및 수주상황"
SEG_ROW = {"음악서비스매출": 39, "용역매출": 36, "상ㆍ제품매출": 33, "합계": 42}
BLUE, GREEN, PURPLE, GREY, RED = 0xC00000, 0x50A014, 0xA03070, 0x777777, 0x2222C0
HDR = 0xF5E9DC
NUM, PCT, WON = "#,##0", "0.0%", "#,##0"


def col(q):
    """분기 → '3. 매출 및 수주상황' 시트 열 (C=2021Q1)."""
    y, qq = int(q[:4]), int(q[-1])
    n = 3 + (y - 2021) * 4 + (qq - 1)
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else "v03"
    out = DIR / f"YG플러스_Analysis template_2026 09_{ver}.xlsx"
    t = pd.read_csv(ROOT / "data" / "ygplus" / "quarterly.csv")
    t = t[(t["n_month"] == 3) & (t["q"] >= "2021Q3")].reset_index(drop=True)
    a = pd.read_csv(ROOT / "data" / "ygplus" / "annual.csv")
    a = a[(a["n_month"] == 12) & (a["year"] >= 2018)].reset_index(drop=True)

    sys.path.insert(0, str(ROOT))
    from evfcf_update import get_work_instance
    from history_ciq_update import retry
    xl = retry(get_work_instance, tries=3, wait=10, label="작업용 엑셀")
    for b in list(xl.Workbooks):
        if not b.Path:
            b.Close(SaveChanges=False)
    for b in list(xl.Workbooks):
        if b.Name.startswith("YG플러스_Analysis"):
            b.Close(SaveChanges=False)
    wb = retry(lambda: xl.Workbooks.Open(str(SRC), UpdateLinks=0), label="open")
    retry(lambda: setattr(xl, "Calculation", -4135), tries=20, wait=3)
    for s in wb.Worksheets:
        if s.Name == "앨범유통 단가":
            xl.DisplayAlerts = False
            s.Delete()
            xl.DisplayAlerts = True
    ws = wb.Worksheets.Add(After=wb.Worksheets(SEG))
    ws.Name = "앨범유통 단가"

    def put(r, c, v, color=None, nf=None, bold=False, size=8, fill=None, formula=False):
        # 엑셀이 바쁘면 0x800AC472 가 나므로 셀 조작 하나하나를 재시도한다
        cell = retry(lambda: ws.Cells(r, c), tries=30, wait=2)
        retry(lambda: setattr(cell, "Formula" if formula else "Value", v), tries=30, wait=2)
        retry(lambda: setattr(cell.Font, "Name", "Arial"), tries=30, wait=2)
        retry(lambda: setattr(cell.Font, "Size", size), tries=30, wait=2)
        if bold:
            retry(lambda: setattr(cell.Font, "Bold", True), tries=30, wait=2)
        if color is not None:
            retry(lambda: setattr(cell.Font, "Color", color), tries=30, wait=2)
        if nf:
            retry(lambda: setattr(cell, "NumberFormatLocal", nf), tries=30, wait=2)
        if fill is not None:
            retry(lambda: setattr(cell.Interior, "Color", fill), tries=30, wait=2)

    put(1, 2, "YG플러스 — 앨범 유통 물량 vs 매출 · 장당 단가", bold=True, size=10)
    put(2, 2, "물음: 앨범이 많이 팔리면 음악서비스매출이 얼마나 늘어나나? 앨범 1장이 돌 때 회사 매출은 얼마인가?", color=GREY)
    put(3, 2, "물량 = 써클차트 월간 앨범차트 톱100 중 유통사 'YG PLUS' 행의 출하량−반품량 합계(장). "
              "매출 = DART 「II.사업의 내용」 매출유형별(초록 = '3. 매출 및 수주상황' 시트 참조, 백만원).", color=GREY)
    put(4, 2, "★ DART 원문: 음악서비스매출 = 음원/음반 유통 + 네이버 음악플랫폼 운영대행. "
              "즉 앨범 유통 수수료는 음악서비스매출 안에 있음(용역매출 아님 — Business 시트 설명 수정 필요).", color=RED)
    put(5, 2, "검증: 1H23 YG PLUS 음반유통 점유율 내 계산 41.5% = DART 공시 41.5% (써클차트 인용) → 방법이 맞음.", color=GREY)

    r = 7
    put(r, 2, "A. 분기별 (물량 = 장, 매출 = 백만원, 단가 = 원/장)", bold=True, fill=HDR)
    hdr = ["분기", "YG PLUS 물량(장)", "시장 톱100 물량(장)", "점유율", "음악서비스매출", "용역매출", "상ㆍ제품매출",
           "합계매출", "음악서비스 원/장", "합계 원/장", "물량 YoY", "음악서비스 YoY"]
    r += 1
    for j, h in enumerate(hdr):
        put(r, 2 + j, h, bold=True, fill=HDR)
    r0 = r + 1
    for i, x in enumerate(t.itertuples()):
        rr = r0 + i
        put(rr, 2, x.q, bold=True)
        put(rr, 3, float(x.units), BLUE, NUM)
        put(rr, 4, float(x.market), BLUE, NUM)
        put(rr, 5, f"=IF(D{rr}>0,C{rr}/D{rr},\"\")", nf=PCT, formula=True)
        for k, name in enumerate(("음악서비스매출", "용역매출", "상ㆍ제품매출", "합계")):
            put(rr, 6 + k, f"='{SEG}'!{col(x.q)}{SEG_ROW[name]}/1000", GREEN, NUM, formula=True)
        put(rr, 10, f"=IF(C{rr}>0,F{rr}*1000000/C{rr},\"\")", nf=WON, formula=True)
        put(rr, 11, f"=IF(C{rr}>0,I{rr}*1000000/C{rr},\"\")", nf=WON, formula=True)
        if i >= 4:
            put(rr, 12, f"=IFERROR(C{rr}/C{rr - 4}-1,\"\")", PURPLE, PCT, formula=True)
            put(rr, 13, f"=IFERROR(F{rr}/F{rr - 4}-1,\"\")", PURPLE, PCT, formula=True)
    r1 = r0 + len(t) - 1
    r = r1 + 2

    put(r, 2, "B. 연간", bold=True, fill=HDR)
    r += 1
    for j, h in enumerate(["연도", "YG PLUS 물량(장)", "시장 톱100 물량(장)", "점유율", "음악서비스매출", "용역매출",
                           "상ㆍ제품매출", "합계매출", "음악서비스 원/장", "합계 원/장"]):
        put(r, 2 + j, h, bold=True, fill=HDR)
    a0 = r + 1
    for i, x in enumerate(a.itertuples()):
        rr = a0 + i
        put(rr, 2, int(x.year), bold=True)
        put(rr, 3, float(x.units), BLUE, NUM)
        put(rr, 4, float(x.market), BLUE, NUM)
        put(rr, 5, f"=IF(D{rr}>0,C{rr}/D{rr},\"\")", nf=PCT, formula=True)
        for k, name in enumerate(("음악서비스매출", "용역매출", "상ㆍ제품매출", "합계")):
            v = getattr(x, {"음악서비스매출": "_5", "용역매출": "_6", "상ㆍ제품매출": "_7", "합계": "_8"}[name], None)
            cells = [f"F{rr2}" if name == "음악서비스매출" else "" for rr2 in ()]
            qs = [rw for rw in range(r0, r1 + 1)]
            put(rr, 6 + k, f"=SUMPRODUCT((LEFT($B${r0}:$B${r1},4)=TEXT($B{rr},\"0\"))*{chr(70 + k)}${r0}:{chr(70 + k)}${r1})",
                nf=NUM, formula=True)
        put(rr, 10, f"=IF(C{rr}>0,F{rr}*1000000/C{rr},\"\")", nf=WON, formula=True)
        put(rr, 11, f"=IF(C{rr}>0,I{rr}*1000000/C{rr},\"\")", nf=WON, formula=True)
    a1 = a0 + len(a) - 1
    r = a1 + 2

    put(r, 2, "C. 관계 (분기, 2021Q3~ 완전분기만)", bold=True, fill=HDR)
    r += 1
    for j, h in enumerate(["항목", "음악서비스매출", "용역매출", "상ㆍ제품매출", "합계매출"]):
        put(r, 2 + j, h, bold=True, fill=HDR)
    lines = [
        ("상관계수 R (물량 vs 매출)", '=CORREL($C${r0}:$C${r1},{c}${r0}:{c}${r1})', "0.00"),
        ("변동 단가 (기울기, 원/장)", '=SLOPE({c}${r0}:{c}${r1},$C${r0}:$C${r1})*1000000', WON),
        ("고정 기반 (절편, 백만원/분기)", '=INTERCEPT({c}${r0}:{c}${r1},$C${r0}:$C${r1})', NUM),
        ("설명력 R²", '=RSQ({c}${r0}:{c}${r1},$C${r0}:$C${r1})', "0.00"),
        ("단순 평균 단가 (원/장)", '=SUM({c}${r0}:{c}${r1})*1000000/SUM($C${r0}:$C${r1})', WON),
    ]
    for lab, f, nf in lines:
        r += 1
        put(r, 2, lab)
        for k in range(4):
            c = chr(70 + k)
            put(r, 3 + k, f.format(r0=r0, r1=r1, c=c), PURPLE, nf, formula=True)
    r += 2

    put(r, 2, "D. 읽는 법 · 결론", bold=True, fill=HDR)
    for line in [
        "· 음악서비스매출은 '고정 기반 + 앨범 연동분'임. 회귀로 나누면 분기당 약 21,600백만원은 앨범과 무관한 기반(네이버 플랫폼 운영대행 + 음원 스트리밍)이고, 앨범이 100만 장 더 돌 때 약 430백만원이 붙음(= 약 430원/장).",
        "· 그래서 '평균 단가'(분기 매출 ÷ 물량)는 앨범이 적은 분기에 커지고 많은 분기에 작아짐 — 단가가 떨어진 게 아니라 고정분이 나눠지는 착시임. 수준보다 기울기를 볼 것.",
        "· 용역매출은 앨범과 상관 없음(R ≈ 0). 전속 매니지먼트·골프행사·모델 대행 매출임.",
        "· 상ㆍ제품매출(MD)은 앨범과 같이 움직임 — 컴백하면 굿즈도 같이 팔리기 때문임. 앨범 100만 장당 약 1,200백만원.",
        "· 점유율: 2021년 25.3% → 2022년 30.8% → 1H23 41.5%(공시 1위) → 2024~25년 30% 안팎. 하이브 물량 이탈 이후 자체 아티스트 사이클에 더 크게 걸려 있음.",
        "· 한계: 써클차트는 톱100만 공개 → 순위 밖 물량이 빠져 물량은 과소, 단가는 과대임. 수준값을 절대치로 쓰지 말고 추세·분기 비교로만 쓸 것.",
        f"· 데이터: 써클차트 월간(2011-01~2026-08, 188개월 전수) · DART 매출유형별(2021Q3~2026Q2) · 작성 {time.strftime('%Y-%m-%d')}.",
    ]:
        r += 1
        put(r, 2, line)

    ws.Columns(1).ColumnWidth = 2
    ws.Columns(2).ColumnWidth = 30
    for c in range(3, 14):
        ws.Columns(c).ColumnWidth = 16
    retry(lambda: setattr(xl, "Calculation", -4105), tries=20, wait=3)
    retry(lambda: xl.CalculateFullRebuild() if False else xl.Calculate(), tries=10, wait=3, label="calc")
    time.sleep(3)
    chk = [(ws.Cells(rr, 10).Text, ws.Cells(rr, 6).Text) for rr in (r0, r1)]
    xl.DisplayAlerts = False
    retry(lambda: wb.SaveAs(str(out), 51), tries=20, wait=5, label="save")
    xl.DisplayAlerts = True
    wb.Close(SaveChanges=False)
    print("저장:", out.name, "| 첫·끝 분기 (원/장, 음악서비스매출):", chk)


if __name__ == "__main__":
    main()
