# -*- coding: utf-8 -*-
"""티커 → 한글 회사명 (DART 기업코드 파일에서 추출한 data/screener/names_kr.csv).

PM 2026-10-21: "English and Korean also can be searched in this site" — 검색 선택지 라벨에
한글명을 같이 넣어 영어·한글 어느 쪽으로 쳐도 찾아지게 한다. 차트 라벨(영문)은 그대로.

names_kr.csv 다시 만들기: DART corpCode.xml(dart-*/corpcode_all.xml) 에서 stock_code 가 있는
행만 뽑으면 된다 (2026-10-21: 상장 3,931개, 스크리너 2,774개 중 2,724개 = 98% 매칭.
안 되는 50개는 A0007C0 처럼 끝이 0이 아닌 코드 = 우선주·외국적·스팩).
"""
from pathlib import Path

import pandas as pd
import streamlit as st

_P = Path(__file__).resolve().parent.parent / "data" / "screener" / "names_kr.csv"


@st.cache_data(show_spinner=False)
def _load(stamp):
    if not _P.exists():
        return {}
    d = pd.read_csv(_P, dtype=str, encoding="utf-8-sig")
    return dict(zip(d["ticker"], d["name_kr"].fillna("")))


def kr_map():
    """{'A005930': '삼성전자', ...}. 파일 없으면 빈 dict."""
    return _load(round(_P.stat().st_mtime, 3) if _P.exists() else 0.0)


def label(company, ticker):
    """검색 라벨: '영문명 · 한글명 (A123456)'. 한글명이 없으면 '영문명 (A123456)'."""
    k = kr_map().get(str(ticker), "")
    return f"{company} · {k} ({ticker})" if k else f"{company} ({ticker})"


def add_labels(df, company_col="company", ticker_col="ticker"):
    """DataFrame 에 company_en · name_kr · label 열을 붙여 돌려준다 (원본 수정 안 함)."""
    d = df.copy()
    m = kr_map()
    d["company_en"] = d[company_col].astype(str)
    d["name_kr"] = d[ticker_col].astype(str).map(m).fillna("")
    d["label"] = [f"{c} · {k} ({t})" if k else f"{c} ({t})"
                  for c, k, t in zip(d["company_en"], d["name_kr"], d[ticker_col].astype(str))]
    return d


# ---------------------------------------------------------------- 표시 언어 (PM 2026-10-21)
# "한글로 검색하면 그래프도 한글, 영어로 검색하면 영어" — 검색창에 친 글자에 한글이 있으면 한글 모드.
# 수동으로 고정하고 싶으면 라디오에서 한글/English 선택. 선택은 session_state 라 페이지를 오가도 유지.
_AUTO = "name_lang_auto"
_PICK = "name_lang_pick"


def note_query(q):
    """검색창 콜백에서 부른다: 입력에 한글이 있으면 한글, 영문자가 있으면 English 로 기억."""
    q = (q or "").strip()
    if not q:
        return
    if any("가" <= ch <= "힣" for ch in q):
        st.session_state[_AUTO] = "한글"
    elif any(ch.isascii() and ch.isalpha() for ch in q):
        st.session_state[_AUTO] = "English"


def lang_control(where=None):
    """라디오(자동 / 한글 / English)를 그리고 지금 쓸 언어를 돌려준다."""
    host = where if where is not None else st
    pick = host.radio("회사 이름", ["자동 (검색어 따라)", "한글", "English"], horizontal=True, key=_PICK,
                      help="자동: 검색창에 한글을 치면 한글, 영어를 치면 영문으로 그래프·표의 회사 이름이 바뀝니다. "
                           "한글명이 없는 회사(외국 상장사 등)는 영문 그대로.")
    if pick == "한글" or pick == "English":
        return pick
    return st.session_state.get(_AUTO, "한글")


def display_names(df, lang):
    """company 열을 선택한 언어로 바꾼 사본. 한글명 없으면 영문 유지. label 은 그대로(검색용)."""
    d = df.copy()
    if "company_en" not in d.columns:
        d = add_labels(d)
    if lang == "한글":
        d["company"] = [k if k else e for k, e in zip(d["name_kr"], d["company_en"])]
    else:
        d["company"] = d["company_en"]
    return d
