# -*- coding: utf-8 -*-
"""선택 종목의 과거 멀티플(TTM)을 공개 데이터로 계산 — 밸류 스크리너 히스토리 차트용.

가격: 네이버 주간 종가(fchart). 재무: DART 연결(CFS) 분기 → TTM 합산, 공시지연 45일 가정.
EV = 시총 + 순부채(최신값 고정 근사). ~/bandchart/band.py 로직을 웹용으로 옮겼다.

DART 키는 코드에 넣지 않는다(공개 저장소) — st.secrets["DART_API_KEY"] 또는
환경변수 DART_API_KEY 에서 읽는다.
"""
import datetime as dt
import io
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import streamlit as st

try:  # 회사 프록시 SSL (로컬 실행용 — 클라우드엔 truststore가 없어 그냥 넘어감)
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

UA = {"User-Agent": "Mozilla/5.0 (buzztrend valuescreener)"}
FUND_START = 2016          # DART 재무 시작 연도 (~10년)
PRICE_WEEKS = 540          # 네이버 주간 종가 ~10년
LAG_DAYS = 45              # 공시 지연 가정


def dart_key() -> str:
    try:
        k = st.secrets.get("DART_API_KEY", "")
    except Exception:
        k = ""
    return k or os.environ.get("DART_API_KEY", "")


@st.cache_resource(ttl=7 * 86400, show_spinner=False)
def _corp_map() -> dict:
    """6자리 종목코드 -> DART corp_code."""
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": dart_key()}, timeout=120, headers=UA)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    xml = z.read(z.namelist()[0]).decode("utf-8")
    out = {}
    for blk in re.finditer(r"<list>(.*?)</list>", xml, re.S):
        b = blk.group(1)
        sc = re.search(r"<stock_code>(\w{6})</stock_code>", b)
        cc = re.search(r"<corp_code>(\d+)</corp_code>", b)
        if sc and cc:
            out[sc.group(1)] = cc.group(1)
    return out


def _prices(ticker6: str):
    r = requests.get("https://fchart.stock.naver.com/sise.nhn",
                     params={"symbol": ticker6, "timeframe": "week",
                             "count": str(PRICE_WEEKS), "requestType": "0"},
                     timeout=30, headers=UA)
    items = re.findall(r'<item data="([^"]+)"', r.text)
    px = []
    for it in items:
        p = it.split("|")
        if p[4]:
            px.append((dt.date(int(p[0][:4]), int(p[0][4:6]), int(p[0][6:8])),
                       float(p[4])))
    return px


def _report_opts():
    y = dt.date.today().year
    return [(y, "11014"), (y, "11012"), (y, "11013"), (y - 1, "11011"), (y - 1, "11014")]


def _shares(corp: str, key: str):
    for yr, rc in _report_opts():
        j = requests.get("https://opendart.fss.or.kr/api/stockTotqySttus.json",
                         params={"crtfc_key": key, "corp_code": corp,
                                 "bsns_year": yr, "reprt_code": rc},
                         timeout=60, headers=UA).json()
        if j.get("status") != "000":
            continue
        # 회사마다 표기가 다르다: '보통주' / '의결권 있는 주식' / '합계' 순으로 찾는다
        for kw in ("보통", "의결권 있는", "합계"):
            for it in j["list"]:
                if kw in (it.get("se") or ""):
                    for f in ("distb_stock_co", "istc_totqy"):
                        v = (it.get(f) or "-").replace(",", "")
                        if v not in ("-", "") and v.isdigit() and int(v) > 0:
                            return int(v)
    raise RuntimeError("주식수 조회 실패")


_CASH_KW = ["현금및현금성자산", "단기금융상품", "단기금융자산", "단기투자자산",
            "금융기관예치금", "기타금융자산"]
_DEBT_KW = ["차입금", "사채", "전환사채", "신주인수권부사채", "교환사채"]


def _netdebt(corp: str, key: str):
    for yr, rc in _report_opts():
        j = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                         params={"crtfc_key": key, "corp_code": corp,
                                 "bsns_year": yr, "reprt_code": rc, "fs_div": "CFS"},
                         timeout=60, headers=UA).json()
        if j.get("status") != "000":
            continue
        cash = debt = 0
        sec = None
        for it in j["list"]:
            if it.get("sj_div") != "BS":
                continue
            nm = (it.get("account_nm") or "").replace(" ", "")
            if nm in ("유동자산", "비유동자산", "유동부채", "비유동부채"):
                sec = nm
                continue
            try:
                v = int((it.get("thstrm_amount") or "").replace(",", ""))
            except ValueError:
                continue
            if sec == "유동자산" and any(k in nm for k in _CASH_KW):
                cash += v
            elif sec in ("유동부채", "비유동부채") and any(k in nm for k in _DEBT_KW) \
                    and "상환" not in nm:
                debt += v
        if cash or debt:
            return debt - cash
    return 0


def _fund_one(args):
    corp, key, yr, rc, qn = args
    try:
        j = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json",
                         params={"crtfc_key": key, "corp_code": corp,
                                 "bsns_year": yr, "reprt_code": rc},
                         timeout=15, headers=UA).json()
    except Exception:
        return None
    if j.get("status") != "000":
        return None
    rec = {}
    for it in j["list"]:
        if it.get("fs_div") != "CFS":
            continue
        nm = it["account_nm"].strip()
        if nm.startswith("당기순이익"):
            nm = "당기순이익"
        if nm in ("매출액", "영업이익", "당기순이익", "자본총계") and nm not in rec:
            s = (it.get("thstrm_amount") or "").replace(",", "")
            rec[nm] = int(s) if s and s != "-" else None
    return ((yr, qn), rec) if rec else None


def _fund(corp: str, key: str):
    """(연도, 분기) -> {매출액, 영업이익, 당기순이익, 자본총계} (연결 CFS, 누적).
    분기 보고서 하나가 요청 하나라 병렬로 받는다 (순차로 하면 40여 번 왕복에
    수십 초씩 걸려서 화면이 멈춘 것처럼 보인다)."""
    jobs = [(corp, key, yr, rc, qn)
            for yr in range(FUND_START, dt.date.today().year + 1)
            for rc, qn in [("11013", 1), ("11012", 2), ("11014", 3), ("11011", 4)]]
    out = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_fund_one, jobs):
            if r:
                out[r[0]] = r[1]
    return out


def _quarterly_rows(fund: dict) -> list:
    """DART 누적 분기 데이터를 '분기 단독' 값으로 변환한 rows 목록."""
    QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    rows = []
    for (yr, qn), rec in sorted(fund.items()):
        v = {"rev": rec.get("매출액"), "ebit": rec.get("영업이익"),
             "ni": rec.get("당기순이익"), "eq": rec.get("자본총계")}
        if qn == 4:  # FY는 누적이라 Q1~Q3를 빼서 4분기 단독값으로
            for k, nmk in [("rev", "매출액"), ("ebit", "영업이익"), ("ni", "당기순이익")]:
                cum, ok = 0, True
                for q2 in (1, 2, 3):
                    q = fund.get((yr, q2), {})
                    if q.get(nmk) is None:
                        ok = False
                        break
                    cum += q[nmk]
                v[k] = (v[k] - cum) if (ok and v[k] is not None) else None
        m, d = QEND[qn]
        rows.append({"date": dt.date(yr, m, d), "q": f"{yr}Q{qn}", **v})
    rows.sort(key=lambda r: r["date"])
    return rows


@st.cache_data(ttl=86400, show_spinner=False)
def load_financials(ticker6: str):
    """분기 실적 DataFrame(date, q, rev, ebit, ni, eq — 분기 단독, KRW) + 메타.
    종목 상세 페이지용 (연결 CFS 기준)."""
    key = dart_key()
    if not key:
        raise RuntimeError("DART_API_KEY가 설정되지 않았습니다")
    corp = _corp_map().get(ticker6)
    if corp is None:
        raise RuntimeError(f"DART에서 종목코드 {ticker6}을 찾을 수 없습니다")
    fund = _fund(corp, key)
    rows = _quarterly_rows(fund)
    if not rows:
        raise RuntimeError("DART 분기 재무 데이터가 없습니다")
    df = pd.DataFrame(rows)
    return df, {"corp_code": corp}


@st.cache_data(ttl=86400, show_spinner=False)
def load_filings(ticker6: str, count: int = 12):
    """최근 공시 목록: [(날짜, 보고서명, 링크)] — DART list API."""
    key = dart_key()
    corp = _corp_map().get(ticker6)
    if not key or corp is None:
        return []
    j = requests.get("https://opendart.fss.or.kr/api/list.json",
                     params={"crtfc_key": key, "corp_code": corp,
                             "bgn_de": (dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d"),
                             "page_count": str(count)},
                     timeout=15, headers=UA).json()
    if j.get("status") != "000":
        return []
    return [(it.get("rcept_dt", ""), it.get("report_nm", ""),
             f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcept_no', '')}")
            for it in j.get("list", [])]


@st.cache_data(ttl=86400, show_spinner=False)
def load_history(ticker6: str):
    """주간 히스토리 DataFrame(date, px, q, per, pbr, evs, eve) + 메타."""
    key = dart_key()
    if not key:
        raise RuntimeError("DART_API_KEY가 설정되지 않았습니다")
    corp = _corp_map().get(ticker6)
    if corp is None:
        raise RuntimeError(f"DART에서 종목코드 {ticker6}을 찾을 수 없습니다")

    px = _prices(ticker6)
    shares = _shares(corp, key)
    nd = _netdebt(corp, key)
    fund = _fund(corp, key)
    rows = _quarterly_rows(fund)

    ttm = []
    for i in range(3, len(rows)):
        w = rows[i - 3:i + 1]
        if any(x[k] is None for x in w for k in ("rev", "ebit", "ni")):
            continue
        ttm.append({"eff": rows[i]["date"] + dt.timedelta(days=LAG_DAYS),
                    "q": rows[i]["q"],
                    "rev": sum(x["rev"] for x in w),
                    "ebit": sum(x["ebit"] for x in w),
                    "ni": sum(x["ni"] for x in w),
                    "eq": rows[i]["eq"]})
    if not ttm:
        raise RuntimeError("재무 TTM 산출 실패 (DART 데이터 부족)")

    # 주식수 단위 오기재 방어 (PBR > 100배는 비현실적 → 1000으로 축소)
    last_eq = next((t["eq"] for t in reversed(ttm) if t["eq"]), None)
    if last_eq:
        while (px[-1][1] / (last_eq / shares)) > 100:
            shares //= 1000

    recs = []
    for d, close in px:
        t = None
        for x in ttm:
            if x["eff"] <= d:
                t = x
            else:
                break
        if t is None:
            continue
        ev = close * shares + nd
        recs.append({
            "date": d, "px": close, "q": t["q"],
            "per": close / (t["ni"] / shares) if t["ni"] and t["ni"] > 0 else None,
            "pbr": close / (t["eq"] / shares) if t["eq"] and t["eq"] > 0 else None,
            "evs": ev / t["rev"] if t["rev"] and t["rev"] > 0 else None,
            "eve": ev / t["ebit"] if t["ebit"] and t["ebit"] > 0 else None,
        })
    df = pd.DataFrame(recs)
    meta = {"shares": shares, "netdebt": nd,
            "quarters": f"{ttm[0]['q']}~{ttm[-1]['q']}",
            "n_weeks": len(df)}
    return df, meta
