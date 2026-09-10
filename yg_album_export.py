# -*- coding: utf-8 -*-
"""YG 워크북(v05d+)에서 앨범·컨센서스 데이터를 뽑아 data/yg/ 에 저장.

Usage:
    python yg_album_export.py [워크북경로]   # 생략 시 폴더에서 최신 파일

산출물:
    album_sales.csv      연도×아티스트 판매량 (Album_Quarterly 연간 합산)
    album_quarterly.csv  분기×아티스트 판매량 + YG 앨범 매출 ₩mn (2024~)
    consensus.csv        연간(2026AS) 매출/영업이익 컨센서스 일별 + 참여 증권사
    consensus_q.csv      분기(3Q26/4Q26) 매출/영업이익 컨센서스 일별
투어는 yg_tour_export.py 담당.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import openpyxl
import pandas as pd

WB_DIR = Path(r"C:\Users\user99i1\LK자산운용\LK자산운용 - 문서\Companies\YG 엔터")
DATA = Path(__file__).resolve().parent / "data" / "yg"


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
        tmp = Path(tempfile.gettempdir()) / "yg_album_copy.xlsx"
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


def export_album(wb):
    """Album_Quarterly -> 분기 CSV(2024~) + 연간 롤업(전 기간)."""
    ws = wb["Album_Quarterly"]
    hdr = [str(c or "").replace(" 장", "").strip()
           for c in next(ws.iter_rows(min_row=3, max_row=3, values_only=True))]
    artists = hdr[1:-2]                      # B..J (마지막 두 열 = Total, YG rev)
    rows = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        q = str(r[0] or "")
        if not q[:4].isdigit():
            continue
        rec = {"quarter": q, "year": int(q[:4])}
        for i, a in enumerate(artists, start=1):
            rec[a] = float(r[i] or 0)
        rec["total"] = float(r[len(artists) + 1] or 0)
        rec["yg_rev_mn"] = float(r[len(artists) + 2] or 0)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df[df["year"] >= 2024].to_csv(DATA / "album_quarterly.csv", index=False,
                                  encoding="utf-8")
    print(f"album_quarterly.csv: {len(df[df['year'] >= 2024])}개 분기 (2024~)")

    # 연간 롤업 -> album_sales.csv (대시보드 연도별 차트용)
    this_year = dt.date.today().year
    out = []
    for yr, g in df.groupby("year"):
        for a in artists:
            v = g[a].sum()
            if v > 0:
                out.append({"year": yr, "is_est": yr > this_year,
                            "artist": a, "copies": v})
        out.append({"year": yr, "is_est": yr > this_year, "artist": "Sum",
                    "copies": g["total"].sum()})
    ya = pd.DataFrame(out)
    ya = ya[ya["copies"] > 0]
    ya.to_csv(DATA / "album_sales.csv", index=False, encoding="utf-8")
    print(f"album_sales.csv: {ya['year'].nunique()}개 연도 "
          f"(Album_Quarterly 연간 합산, {this_year + 1}년~ = 추정)")


def _consensus_frame(ws):
    """콴티와이즈 컨센서스 시트 -> (base_dates, 일별 DataFrame)."""
    bases, items = [], []
    for r in ws.iter_rows(min_row=1, max_row=14, values_only=True):
        label = str(r[0] or "")
        if label.startswith("Base Date"):
            bases = [str(x or "") for x in r[1:]]
        if label.replace(" ", "").startswith("DATE"):
            items = [str(x or "") for x in r[1:]]
            break
    rows = []
    for r in ws.iter_rows(min_row=15, values_only=True):
        if r[0] is None:
            continue
        try:
            d = pd.Timestamp(r[0]).date().isoformat()
        except Exception:
            continue
        rows.append((d, r[1:1 + len(bases)]))
    return bases, items, rows


def export_consensus(wb):
    # 연간 (Consensus 또는 vs CONSEN 시트: 2026AS 매출/영업이익 + 참여 증권사 수)
    _annual = next((n for n in ("Consensus", "vs CONSEN") if n in wb.sheetnames),
                   None)
    if _annual is None:
        raise SystemExit("연간 컨센서스 시트를 찾지 못했습니다")
    b, it, rows = _consensus_frame(wb[_annual])
    out_annual = []
    for d, vals in rows:
        rec = {"date": d}
        for base, item, v in zip(b, it, vals):
            if not isinstance(v, (int, float)):
                continue
            if "매출" in item and "AS" in base:
                rec["rev_eok"] = v / 1e5
            elif "영업" in item and "AS" in base:
                rec["op_eok"] = v / 1e5
            elif "매출" in item and "증권사" in item:
                rec["n_rev"] = v
        if "n_rev" not in rec:      # 구권 시트: D/E열이 증권사 수
            for item, v in zip(it, vals):
                if "증권사" in item and isinstance(v, (int, float)):
                    rec["n_rev"] = v
                    break
        if "rev_eok" in rec:
            out_annual.append(rec)
    pd.DataFrame(out_annual).to_csv(DATA / "consensus.csv", index=False,
                             encoding="utf-8")
    print(f"consensus.csv: {len(out_annual)}일 (연간 2026AS)")

    # 분기+연간 (vs CONSENSUS 시트: 2026AS + 202609 + 202612)
    b, it, rows = _consensus_frame(wb["vs CONSENSUS"])
    out = []
    annual2 = []
    for d, vals in rows:
        rec = {"date": d}
        rec_a = {"date": d}
        for base, item, v in zip(b, it, vals):
            if not isinstance(v, (int, float)):
                continue
            key = None
            if "매출" in item:
                key = {"202609": "rev3q_eok", "202612": "rev4q_eok"}.get(base)
                if "AS" in base:
                    rec_a["rev_eok"] = v / 1e5
            elif "영업" in item:
                key = {"202609": "op3q_eok", "202612": "op4q_eok"}.get(base)
                if "AS" in base:
                    rec_a["op_eok"] = v / 1e5
            if key:
                rec[key] = v / 1e5
        if len(rec) > 1:
            out.append(rec)
        if "rev_eok" in rec_a:
            annual2.append(rec_a)
    pd.DataFrame(out).to_csv(DATA / "consensus_q.csv", index=False,
                             encoding="utf-8")
    # 연간: 최신 시트(vs CONSENSUS)가 더 길면 그걸 쓰고 증권사 수만 병합
    if annual2:
        a2 = pd.DataFrame(annual2)
        a1 = pd.DataFrame(out_annual)
        if len(a2) >= len(a1):
            merged = a2.merge(a1[["date", "n_rev"]] if "n_rev" in a1.columns
                              else a1[["date"]], on="date", how="left")
            merged.to_csv(DATA / "consensus.csv", index=False, encoding="utf-8")
            print(f"consensus.csv: vs CONSENSUS 기준으로 갱신 ({len(merged)}일, "
                  f"~{merged['date'].max()})")
    last = out[-1] if out else {}
    print(f"consensus_q.csv: {len(out)}일 | 최신 3Q 매출 "
          f"{last.get('rev3q_eok', 0):,.0f}억 / 4Q {last.get('rev4q_eok', 0):,.0f}억")


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_workbook()
    print("워크북:", path.name)
    wb = open_workbook(path)
    export_album(wb)
    export_consensus(wb)
    print("완료: git add data/yg && commit && push")


if __name__ == "__main__":
    main()
