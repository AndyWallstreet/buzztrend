# -*- coding: utf-8 -*-
"""KRX 저PBR 기업 명단 → 사이트 데이터 + 엑셀.

KRX publishes the list on KIND (기업 밸류업 → 저PBR기업) every May and November.
Inputs (saved from the KIND page, see data/screener/lowpbr/):
  raw_<YYYYMMDD>.csv         번호,시장,회사명,PBR(배),GICS업종,PBR기준일,결산월
  kind_codes_<YYYYMMDD>.txt  회사명=KIND 발행사코드(5자리);...   ticker = 'A' + code + '0'
Outputs:
  data/screener/lowpbr/lowpbr_latest.csv   — the 밸류 스크리너 page reads this
  ~/lowpbr/저PBR기업_KRX_<YYYYMMDD>.xlsx   — Excel copy for the PM

Usage:  python lowpbr_update.py 20261102
"""
import html
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
SCR = ROOT / "data" / "screener"
LP = SCR / "lowpbr"
OUT_XL = Path.home() / "lowpbr"

day = sys.argv[1] if len(sys.argv) > 1 else "20261102"
list_date = f"{day[:4]}-{day[4:6]}-{day[6:]}"

raw = pd.read_csv(LP / f"raw_{day}.csv", encoding="utf-8-sig", dtype=str)
codes = dict(x.split("=") for x in
             (LP / f"kind_codes_{day}.txt").read_text(encoding="utf-8").strip().split(";"))
raw["ticker"] = "A" + raw["회사명"].map(codes) + "0"
assert raw["ticker"].notna().all(), "KIND 코드 없는 회사가 있음"

# 이름 검산 — DART 이름과 다르면 (사명 변경 등) 알려만 준다
nk = pd.read_csv(SCR / "names_kr.csv", encoding="utf-8-sig", dtype=str)
nk["name_kr"] = nk["name_kr"].map(html.unescape)
nm = dict(zip(nk["ticker"], nk["name_kr"]))
for _, r in raw[raw["ticker"].map(nm) != raw["회사명"]].iterrows():
    print(f"  이름 다름: {r['회사명']} ({r['ticker']}) — DART 목록 이름 {nm.get(r['ticker'])}")

out = pd.DataFrame({
    "ticker": raw["ticker"],
    "name_kr": raw["회사명"],
    "market": raw["시장"],
    "krx_pbr": raw["PBR(배)"].astype(float),
    "gics_kr": raw["GICS업종"],
    "pbr_date": raw["PBR기준일"],
    "fy_end": raw["결산월"],
    "list_date": list_date,
})
out.to_csv(LP / "lowpbr_latest.csv", index=False, encoding="utf-8-sig")
print(f"사이트 데이터: {len(out)}개사 → {LP / 'lowpbr_latest.csv'}")

# ---------------------------------------------------------------- Excel
scr = pd.read_csv(SCR / "screener_data.csv", encoding="utf-8-sig", dtype={"ticker": str})
scr = scr.drop_duplicates("ticker").set_index("ticker")
cov = pd.read_csv(SCR.parent / "coverage" / "coverage.csv", encoding="utf-8-sig", dtype=str)
cov_t = set("A" + cov["ticker"].str.zfill(6))
import json
as_of = json.loads((SCR / "meta.json").read_text(encoding="utf-8")).get("as_of", "")

F = "Arial"
body, bold = Font(name=F, size=8), Font(name=F, size=8, bold=True)
title = Font(name=F, size=10, bold=True)
blue = Font(name=F, size=8, color="0000FF")          # 원본 값 (하드코딩)
head_fill = PatternFill("solid", fgColor="D9E1F2")
cov_fill = PatternFill("solid", fgColor="FFF2CC")

wb = Workbook()
ws = wb.active
ws.title = "저PBR_명단"
ws["A1"] = f"KRX 저PBR 기업 명단 ({list_date} 공표, {len(out)}개사)"
ws["A1"].font = title
ws["A2"] = ("출처: KRX KIND 기업 밸류업 → 저PBR기업 (kind.krx.co.kr). 파란 글씨 = 원본 값. "
            f"현재 PBR·ROIC+SG·PER·시총 = 밸류 스크리너 데이터 (Cap IQ, 기준일 {as_of}). 노란 줄 = 내 커버리지 종목.")
ws["A2"].font = body
hdr = ["번호", "티커", "시장", "회사명", "KRX PBR (x)", "GICS 업종", "PBR 기준일", "결산월",
       "현재 PBR (x)", "ROIC+SG (%)", "PER (x)", "시총 (KRWbn)", "커버리지", "Comment"]
R0 = 4
for j, h in enumerate(hdr, 1):
    c = ws.cell(R0, j, h)
    c.font, c.fill = bold, head_fill
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
for i, r in out.reset_index(drop=True).iterrows():
    row = R0 + 1 + i
    s = scr.loc[r["ticker"]] if r["ticker"] in scr.index else None
    num = lambda col: (float(s[col]) if s is not None and pd.notna(s[col]) else None)
    roic = num("roic_sg")
    mcap = num("mcap")
    vals = [i + 1, r["ticker"], r["market"], r["name_kr"], r["krx_pbr"], r["gics_kr"],
            r["pbr_date"], r["fy_end"], num("pbr"),
            round(roic * 100, 1) if roic is not None else None,
            num("per"), round(mcap / 1000) if mcap is not None else None,
            "Y" if r["ticker"] in cov_t else "", ""]
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v)
        c.font = blue if j in (2, 3, 4, 5, 6, 7, 8) else body
        if r["ticker"] in cov_t:
            c.fill = cov_fill
    ws.cell(row, 1).number_format = "0"
    ws.cell(row, 5).number_format = "0.00"
    ws.cell(row, 9).number_format = "0.00"
    ws.cell(row, 10).number_format = "0.0"
    ws.cell(row, 11).number_format = "0.0"
    ws.cell(row, 12).number_format = "#,##0"
    if r["name_kr"] != nm.get(r["ticker"]):
        ws.cell(row, 14, f"DART 목록상 이전 이름: {nm.get(r['ticker'])}").font = body
last = R0 + len(out)
ws.freeze_panes = ws.cell(R0 + 1, 5)
ws.auto_filter.ref = f"A{R0}:{get_column_letter(len(hdr))}{last}"
for j, w in enumerate([5, 9, 7, 18, 9, 16, 10, 6, 9, 9, 8, 10, 7, 30], 1):
    ws.column_dimensions[get_column_letter(j)].width = w

# 요약 시트 — 전부 명단 시트를 가리키는 수식
sm = wb.create_sheet("요약")
sm["A1"] = "요약 (명단 시트에서 수식으로 계산)"
sm["A1"].font = title
rng = lambda col: f"저PBR_명단!${col}${R0 + 1}:${col}${last}"
rows = [("구분", "회사 수", "평균 KRX PBR (x)", "Comment")]
for lab, crit in (("전체", None), ("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")):
    if crit is None:
        rows.append((lab, f"=COUNTA({rng('B')})", f"=AVERAGE({rng('E')})", "뉴스 보도: 151개사, 평균 0.247배"))
    else:
        rows.append((lab, f'=COUNTIF({rng("C")},"{crit}")',
                     f'=AVERAGEIF({rng("C")},"{crit}",{rng("E")})', "뉴스 보도: 96 / 55" if lab == "KOSPI" else ""))
rows.append(("", "", "", ""))
rows.append(("GICS 업종", "회사 수", "평균 KRX PBR (x)", ""))
for g in out["gics_kr"].value_counts().index:
    rows.append((g, f'=COUNTIF({rng("F")},"{g}")', f'=AVERAGEIF({rng("F")},"{g}",{rng("E")})', ""))
for i, rr in enumerate(rows, 3):
    for j, v in enumerate(rr, 1):
        c = sm.cell(i, j, v)
        c.font = bold if rr[0] in ("구분", "GICS 업종") else body
        if rr[0] in ("구분", "GICS 업종"):
            c.fill = head_fill
        if j == 2:
            c.number_format = "0"
        if j == 3:
            c.number_format = "0.00"
for j, w in enumerate([18, 9, 14, 30], 1):
    sm.column_dimensions[get_column_letter(j)].width = w

# 선정 기준 메모
nt = wb.create_sheet("선정기준")
notes = [
    "선정 기준 (KRX / 언론 보도, 2026-11-01~02)",
    "· PBR 1배 미만 명단이 아님. 시장·업종(GICS 11개)별 PBR 이 최근 3년 하위 25% (KOSPI) / 하위 10% (KOSDAQ) 인 회사.",
    "· 요건 해당 185개사 (KOSPI 115, KOSDAQ 70) 중 10/22 까지 기업가치 제고 계획을 공시한 34개사는 제외 → 151개사.",
    "· 공시 7거래일 전까지 PBR 개선계획을 내면 1년간 제외. 단 12개 반기 연속 (또는 13개 중 12개) 해당 기업은 공시해도 포함.",
    "· 공표 기간: 2026-11-02 ~ 2027-05-04 (다음 명단). 이후 매년 5월·11월 공표.",
    "· HTS·MTS 종목에 '저PBR' 표시가 붙음. 151개사 전체에 2027년 1:1 PBR 개선 컨설팅 지원.",
    "",
    "출처",
    "KIND 저PBR기업: https://kind.krx.co.kr/valueup/lowpbr.do?method=valueupLowpbrMain",
    "머니투데이 2026-11-01: https://www.mt.co.kr/stock/2026/11/01/2026103118495968867",
    "디지털데일리 2026-11-02: https://www.ddaily.co.kr/page/view/2026110210115902416",
]
nt["A1"].font = title
for i, t in enumerate(notes, 1):
    nt.cell(i, 1, t).font = title if i == 1 else (bold if t == "출처" else body)
nt.column_dimensions["A"].width = 120

OUT_XL.mkdir(exist_ok=True)
xl = OUT_XL / f"저PBR기업_KRX_{day}.xlsx"
wb.save(xl)
print(f"엑셀: {xl}")
