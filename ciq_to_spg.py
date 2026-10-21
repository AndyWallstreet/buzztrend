# -*- coding: utf-8 -*-
"""비교기업 워크북의 죽은 CIQ() 수식을 Capital IQ Pro SPG() 수식으로 바꿔 새 버전 파일로 저장.

왜 (PM 2026-10-21): 2026-09-11 오피스 업데이트 뒤 옛 Capital IQ 플러그인(CIQ)이 로드되지 않아
  v04/v05 Data 시트의 수식 70%가 #NAME? 가 됨. 새 애드인 함수 SPG() 는 정상.
어떻게: xlsx(zip) 안의 시트 XML 에서 수식 텍스트만 바꾼다 (엑셀을 열지 않음 → 원본 무손상,
  서식·차트·슬라이서 그대로). 결과 파일은 처음 열면 #PEND 상태이며 S&P 리본의 Refresh 로 값이 채워짐.

문법 차이 (2026-10-21 작업용 엑셀에서 직접 검증, 메모리 capiq-pro-spg-formulas 참고):
  - LTM 은 문자열 "LTM" 만 통함 (IQ_LTM=2000 숫자는 TEV 계열에서 실패). FY/FY-1/FQ 는 정의된 이름(숫자) 그대로 OK.
  - PER/PBR/PTBV 는 기간 인자 없이 (ticker, 코드, 날짜). PBV·PTBV 는 100배로 오므로 /100.
  - 통화 인자(Ccy, Conv) 는 없음 → 제거. 원래 통화(KRW) 로 옴.
  - 코드가 바뀐 것: IQ_PERIODDATE→IQ_PERIOD_END, IQ_SHARESOUTSTANDING→SP_SHARES_OUT, IQ_LASTSALEPRICE→SP_LASTSALEPRICE,
    IQ_YEARHIGH/LOW→SP_PRICE_HIGH/LOW(,,"52W"), IQ_MARKETCAP→SP_MARKETCAP, IQ_COMPANY_NAME→SP_COMPANY_NAME,
    IQ_TOTAL_DEBT_EQUITY→IQ_DEBT_TO_EQUITY, IQ_TOTAL_DEBT_CAPITAL→IQ_DEBT_TO_CAPITAL, IQ_PREF_EQUITY→IQ_TOTAL_PREF_EQUITY,
    IQ_RETURN_EQUITY→IQ_ROE, IQ_TEV_*_FWD→SP_TEV_*_FWD, IQ_PE_EXCL_FWD→SP_PE_FWD.
  - ROIC 코드는 SPG 에 없음 → EBIT×(1−세율)/(자본+차입−현금) 을 LET 수식으로 (사이트 스크리너와 같은 정의).
  - CIQGETDATE(IQ_TODAY) → WORKDAY(TODAY(),-1) (당일 기준 PBV 는 NA 라서 직전 영업일).
  - 선행 배수(SP_*_FWD, SP_PE_FWD) 는 날짜 없이 현재값 (날짜를 주면 소형주 대부분 NA).
  - 주식수는 SPG 가 '주' 단위라 /1,000,000 해서 CIQ 와 같은 백만 주 단위 유지.

Usage:  python ciq_to_spg.py <원본.xlsx> <출력.xlsx>
"""
import html
import re
import sys
import zipfile
from collections import Counter

CIQ = "_xll.ciqfunctions.udf.CIQ("
SPG = "_xll.SNL.Clients.Office.Excel.Functions.SPG("
GETDATE = "_xll.ciqfunctions.udf.CIQGETDATE("

LTM_TOKENS = {"IQ_LTM", '"IQ_LTM"'}
TEV_LTM = re.compile(r"^IQ_TEV_(TOTAL_REV|EBIT|EBITDA)(_EXER|_OUT)?$")
FWD = re.compile(r"^IQ_(TEV_(TOTAL_REV|EBIT|EBITDA)_FWD(_EXER|_OUT)?|PE_EXCL_FWD)$")
RENAME = {
    "IQ_PERIODDATE": "IQ_PERIOD_END",
    "IQ_TOTAL_DEBT_EQUITY": "IQ_DEBT_TO_EQUITY",
    "IQ_TOTAL_DEBT_CAPITAL": "IQ_DEBT_TO_CAPITAL",
    "IQ_PREF_EQUITY": "IQ_TOTAL_PREF_EQUITY",
    "IQ_RETURN_EQUITY": "IQ_ROE",
}
# 기간 인자가 (숫자 코드 | "LTM") 인 일반 재무 항목
PERIOD_FAMILY = {
    "IQ_TOTAL_REV", "IQ_GROSS_MARGIN", "IQ_EBITDA_MARGIN", "IQ_NI_MARGIN", "IQ_DAYS_SALES_OUT",
    "IQ_DAYS_INVENTORY_OUT", "IQ_DAYS_PAYABLE_OUT", "IQ_CASH_CONVERSION", "IQ_ASSET_TURNS",
    "IQ_FIXED_ASSET_TURNS", "IQ_AR_TURNS", "IQ_INVENTORY_TURNS", "IQ_CURRENT_RATIO", "IQ_QUICK_RATIO",
    "IQ_CASH_ST_INVEST", "IQ_TOTAL_DEBT", "IQ_MINORITY_INTEREST_TOTAL",
    "IQ_PERIOD_END", "IQ_DEBT_TO_EQUITY", "IQ_DEBT_TO_CAPITAL", "IQ_TOTAL_PREF_EQUITY", "IQ_ROE",
}
DATE_ONLY = {"IQ_PE_EXCL", "IQ_PBV", "IQ_PTBV", "IQ_SHARESOUTSTANDING_EXER", "IQ_SHARESOUTSTANDING_OUT"}
DIV100 = {"IQ_PBV", "IQ_PTBV"}

stats = Counter()


def split_args(s):
    """최상위 콤마로 인자 분리 (따옴표·괄호 안의 콤마는 무시)."""
    out, depth, q, cur = [], 0, False, []
    for ch in s:
        if ch == '"':
            q = not q
        elif not q:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    out.append("".join(cur).strip())
    return out


def find_call(text, start, head):
    """head 로 시작하는 호출의 (시작, 인자문자열, 끝+1) — 괄호 짝 맞춰 찾기."""
    i = text.find(head, start)
    if i < 0:
        return None
    j = i + len(head); depth = 1; q = False
    while j < len(text):
        ch = text[j]
        if ch == '"':
            q = not q
        elif not q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i, text[i + len(head):j], j + 1
        j += 1
    raise ValueError("괄호 짝이 안 맞음: " + text[i:i + 80])


def period_arg(p):
    p = p.strip()
    if p in LTM_TOKENS:
        return '"LTM"'
    return p  # IQ_FY / IQ_FY- 1 / IQ_FQ / "CY2026" 등은 그대로 (정의된 이름 = 숫자 코드)


def cy_expr(p, date):
    """IQ_CY+1 → "CY"&(YEAR(date)+1) ; "CY2026" 같은 리터럴은 그대로."""
    m = re.fullmatch(r"IQ_CY\s*([+-])\s*(\d+)", p.strip())
    if m:
        return f'"CY"&(YEAR({date}){m.group(1)}{m.group(2)})'
    return p.strip()


def roic_let(t, date):
    # 파일 XML 에서 LET 은 _xlfn.LET, 변수 이름은 _xlpm. 접두사가 필수 (없으면 엑셀이 파일을 못 염)
    s = SPG; e_, t_, ic = "_xlpm.e", "_xlpm.t", "_xlpm.ic"
    return (f'_xlfn.LET({e_},{s}{t},"IQ_EBIT","LTM",{date}),'
            f'{t_},IFERROR(MIN(MAX({s}{t},"IQ_EFFECT_TAX_RATE","LTM",{date}),0),40),25),'
            f'{ic},{s}{t},"IQ_TOTAL_EQUITY",500,{date})+IFERROR({s}{t},"IQ_TOTAL_DEBT",500,{date}),0)'
            f'-IFERROR({s}{t},"IQ_CASH_ST_INVEST",500,{date}),0),'
            f'IF(NOT(ISNUMBER({e_})),"NA",IF({ic}<=0,"NM",{e_}*(1-{t_}/100)/{ic}*100)))')


def convert_call(args, sheet):
    """CIQ 인자 리스트 → SPG 호출 문자열."""
    t = args[0]
    m = args[1].strip()
    rest = [a for a in args[2:]]
    # 통화 인자 제거 (Ccy, Conv 또는 끝의 빈 인자)
    while rest and rest[-1] in ("Ccy", "Conv", ""):
        rest.pop()
    if not m.startswith('"'):  # Mult History: 코드가 셀에 있음 ($C$9)
        stats["cell-mnemonic"] += 1
        date = rest[1] if len(rest) > 1 else rest[0]
        return (f'_xlfn.LET(_xlpm.v,IF(LEFT({m},6)="IQ_TEV",{SPG}{t},{m},"LTM",{date}),{SPG}{t},{m},{date})),'
                f'IF({m}="IQ_PBV",IFERROR(_xlpm.v/100,"NA"),_xlpm.v))')
    code = m.strip('"')
    stats[code] += 1
    if code == "IQ_RETURN_INVESTED_CAPITAL":
        return roic_let(t, rest[1])
    if TEV_LTM.match(code):
        return f'{SPG}{t},"{code}","LTM",{rest[1]})'
    if FWD.match(code):
        # 날짜를 넣으면 소형주는 'NA' (추정치 시계열이 없음, A177900 등) → 날짜 없이 '현재' 선행 배수로 받는다
        new = "SP_PE_FWD" if code == "IQ_PE_EXCL_FWD" else "SP_" + code[3:]
        return f'{SPG}{t},"{new}",{cy_expr(rest[0], rest[1])})'
    if code in DATE_ONLY:
        date = rest[-1] if rest else None
        body = f'{SPG}{t},"{code}",{date})' if date else f'{SPG}{t},"{code}")'
        if code in DIV100:
            return f'IFERROR({body}/100,"NA")'
        if code.startswith("IQ_SHARESOUTSTANDING"):  # SPG 는 주 단위, CIQ 는 백만 주 → 시트 단위(백만) 유지
            return f'IFERROR({body}/1000000,"NA")'
        return body
    if code == "IQ_SHARESOUTSTANDING":
        return f'IFERROR({SPG}{t},"SP_SHARES_OUT",{rest[0]})/1000000,"NA")'
    if code == "IQ_LASTSALEPRICE":
        return f'{SPG}{t},"SP_LASTSALEPRICE",{rest[0]})'
    if code in ("IQ_YEARHIGH", "IQ_YEARLOW"):
        new = "SP_PRICE_HIGH" if code == "IQ_YEARHIGH" else "SP_PRICE_LOW"
        return f'{SPG}{t},"{new}",{rest[0]},"52W")'
    if code == "IQ_MARKETCAP":
        return f'{SPG}{t},"SP_MARKETCAP"' + (f',{rest[0]})' if rest else ")")
    if code == "IQ_COMPANY_NAME":
        return f'{SPG}{t},"SP_COMPANY_NAME")'
    if code == "IQ_QUICK_COMP":  # SPG 에 없는 기능 (템플릿 잔재, IF 의 안 타는 가지)
        return f'{SPG}{t},"IQ_QUICK_COMP")'
    code2 = RENAME.get(code, code)
    if code2 in PERIOD_FAMILY:
        p = period_arg(rest[0])
        return f'{SPG}{t},"{code2}",{p}' + (f',{rest[1]})' if len(rest) > 1 and rest[1] else ")")
    raise KeyError(f"매핑 없는 코드: {code} ({sheet})")


def convert_formula(f, sheet):
    out = f
    while True:
        hit = find_call(out, 0, CIQ)
        if not hit:
            break
        i, inner, j = hit
        out = out[:i] + convert_call(split_args(inner), sheet) + out[j:]
    while True:
        hit = find_call(out, 0, GETDATE)
        if not hit:
            break
        i, inner, j = hit
        # 오늘 날짜로는 IQ_PBV/IQ_PTBV 가 'NA' (당일 데이터 미반영) → 직전 영업일을 기준일로
        out = out[:i] + "WORKDAY(TODAY(),-1)" + out[j:]
        stats["CIQGETDATE"] += 1
    return out


def convert_sheet_xml(xml, sheet):
    def repl(m):
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if "ciqfunctions" not in body:
            return m.group(0)
        new = convert_formula(html.unescape(body), sheet)
        return head + html.escape(new, quote=False) + tail
    return re.sub(r"(<f\b[^>]*>)([^<]*)(</f>)", repl, xml)


def main(src, dst):
    zin = zipfile.ZipFile(src)
    zout = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    wb = zin.read("xl/workbook.xml").decode("utf8")
    rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf8")
    rid2t = {m.group(1): m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)}
    rid2t.update({m.group(2): m.group(1) for m in re.finditer(r'Target="([^"]+)"[^>]*Id="(rId\d+)"', rels)})
    path2name = {}
    for n, r in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb):
        path2name["xl/" + rid2t[r].lstrip("/").replace("xl/", "")] = html.unescape(n)
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename in path2name and b"ciqfunctions" in data:
            xml = data.decode("utf8")
            before = xml.count("ciqfunctions")
            xml = convert_sheet_xml(xml, path2name[item.filename])
            print(f"  {path2name[item.filename]:14s} CIQ {before:7d} -> 남은 ciqfunctions {xml.count('ciqfunctions')}")
            data = xml.encode("utf8")
        zout.writestr(item, data)
    zout.close()
    print("코드별 변환 건수:", dict(stats))
    print("저장:", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
