# -*- coding: utf-8 -*-
"""YG 워크북(v05d+)에서 투어 데이터를 뽑아 data/yg/*.csv 로 저장.

v2 (2026-09-07): 워크북이 Tour_drivers(지역 6개 Bull/Base/Bear → Applied)로
스탑별 YG 매출까지 계산하므로, 여기서는 재계산하지 않고 **워크북의 계산값을
그대로 내보낸다** (Tour detail X열 = YG rev ₩mn).

산출물:
    {group}_tour.csv     그룹별 2026+ 스탑 목록 (사이트 투어 트래커용)
    tour_quarterly.csv   Tour_Quarterly — 분기별 아티스트별 YG 투어 매출 (₩mn)
    assumptions.json     Tour_drivers의 지역별 Applied 가격/배분/마진 + FX 등
"""
import json
import sys
from pathlib import Path

import openpyxl
import pandas as pd

WB_DIR = Path(r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\YG 엔터")
DATA = Path(__file__).resolve().parent / "data" / "yg"

TARGETS = {  # group -> 시작 연도, 파일명
    "BIGBANG": (2026, "bigbang_tour.csv"),
    "BABYMONSTER": (2026, "babymonster_tour.csv"),
    "TREASURE": (2026, "treasure_tour.csv"),
    "BLACKPINK": (2026, "blackpink_tour.csv"),
}


def latest_workbook() -> Path:
    cands = sorted(WB_DIR.glob("YG 엔터_Analysis template_*.xlsx"),
                   key=lambda p: p.stat().st_mtime)
    if not cands:
        raise SystemExit("YG 워크북을 찾지 못했습니다")
    return cands[-1]


def open_workbook(path: Path):
    try:
        return openpyxl.load_workbook(path, read_only=True, data_only=True)
    except PermissionError:
        import shutil
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "yg_export_copy.xlsx"
        try:
            shutil.copy(path, tmp)
        except PermissionError:
            # 엑셀이 독점 잠금 중 — 라이브 엑셀에 사본 저장을 부탁한다
            import win32com.client as win32
            xl = win32.GetActiveObject("Excel.Application")
            done = False
            for w in xl.Workbooks:
                if w.Name == path.name:
                    w.SaveCopyAs(str(tmp))
                    done = True
                    break
            if not done:
                raise
        print(f"워크북이 잠겨 있어 사본으로 읽음: {tmp}")
        return openpyxl.load_workbook(tmp, read_only=True, data_only=True)


def export_tours(wb):
    """Tour detail — 워크북 계산값(스탑별 YG 매출 포함)을 그룹별 CSV로."""
    ws = wb["Tour detail"]
    rows = ws.iter_rows(min_row=4, values_only=True)
    out = {g: [] for g in TARGETS}
    for r in rows:
        g, tour, year = r[0], r[1], r[2]
        if g not in TARGETS or not year or int(year) < TARGETS[g][0]:
            continue
        cap = float(r[11] or 0)
        shows = float(r[12] or 0)
        out[g].append({
            "group": g, "tour": tour,
            "date": str(r[6])[:10], "month": r[4], "quarter": r[5],
            "city": r[7], "country": r[8], "region": r[9], "venue": r[10],
            "capacity": int(cap), "shows": int(shows),
            "seats": int(cap * shows),
            "price_usd": r[19],                       # T: Price $ (드라이버 반영)
            "taking": None,                            # 지역별 배분율은 assumptions 참조
            "att_est": round(float(r[17] or 0), 0),    # R: Attendance used
            "gross_usd_m": round(float(r[21] or 0), 3) if r[21] else None,  # V
            "yg_rev_usd_m": round(float(r[22] or 0), 3) if r[22] else None, # W
            "yg_rev_krw_mn": round(float(r[23] or 0), 1) if r[23] else 0,   # X
            "ref": r[25] or "",
        })
    for g, (start, fname) in TARGETS.items():
        df = pd.DataFrame(out[g])
        if not len(df):
            print(f"{g}: {start}년 이후 스탑 없음 — {fname} 생략")
            continue
        df = df.sort_values("date")
        df.to_csv(DATA / fname, index=False, encoding="utf-8-sig")
        print(f"{fname}: {len(df)}개 스탑, YG 매출 "
              f"{df['yg_rev_krw_mn'].sum() / 100:,.0f}억원 (워크북 계산값)")


def export_quarterly(wb):
    ws = wb["Tour_Quarterly"]
    rows = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        q = str(r[0] or "")
        if not q[:4].isdigit() or int(q[:4]) < 2024:
            continue
        rows.append({"quarter": q, "attendance": r[1],
                     "BIGBANG": r[2], "BLACKPINK": r[3],
                     "BABYMONSTER": r[4], "TREASURE": r[5],
                     "total_mn": r[6]})
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "tour_quarterly.csv", index=False, encoding="utf-8")
    print(f"tour_quarterly.csv: {len(df)}개 분기 (2024~)")
    return df


def export_drivers(wb):
    """Tour_drivers — 지역 6개 Applied 벡터 + 글로벌 파라미터."""
    ws = wb["Tour_drivers"]
    v = {}
    for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=86, max_col=10,
                                          values_only=True), start=1):
        for ci, val in enumerate(row, start=1):
            v[(ri, ci)] = val
    regions = [v[(67, c)] for c in range(3, 9)]           # C67:H67
    def row_vals(r):
        return {reg: v[(r, c)] for reg, c in zip(regions, range(3, 9))}
    assum = {
        "scenario": str(v[(3, 3)] or "").strip(),
        "fx": v[(7, 8)],                                  # H7 Applied FX
        "ticket_inflation": v[(57, 3)],
        "taking_world": v[(61, 3)], "taking_jp": v[(62, 3)],
        "taking_kr": v[(63, 3)],
        "regions": {reg: {"price_usd": row_vals(72)[reg],
                          "allocation": row_vals(77)[reg],
                          "margin": row_vals(82)[reg]} for reg in regions},
        "price_x_alloc": row_vals(84),
        "price_x_alloc_x_margin": row_vals(85),
    }
    (DATA / "assumptions.json").write_text(
        json.dumps(assum, ensure_ascii=False, indent=1), encoding="utf-8")
    print("assumptions.json: 시나리오", assum["scenario"], "| 지역", regions)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_workbook()
    print("워크북:", path.name)
    wb = open_workbook(path)
    export_tours(wb)
    export_quarterly(wb)
    export_drivers(wb)
    print("완료 — git add data/yg && commit && push")


if __name__ == "__main__":
    main()
