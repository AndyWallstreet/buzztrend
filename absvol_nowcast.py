# -*- coding: utf-8 -*-
"""절대검색량 '최신 달 속보' — 전세계(WW) 숫자가 나라별보다 먼저 나왔을 때 쓰는 추정.

왜 (PM 2026-10-15): DataForSEO 는 전세계 숫자(구글애즈, 12개월)를 나라별(16개국,
    8년치)보다 먼저 올린다. 나라별 9월치를 기다리는 동안 전세계 9월치로 방향을 미리 본다.

방법: 두 데이터가 겹치는 최근 3개월의 '16개국 합 ÷ 전세계' 비율로 전세계 최신 달을
    16개국 기준으로 바꾼다. 두 숫자는 출처가 달라 크기가 다르므로 그대로 이어 붙이면 안 된다.

원본(absvol_monthly.csv)에는 절대 섞지 않는다 — 퍼널·스크리너 계산이 오염된다.
나라별 최신 달이 전세계를 따라잡으면 빈 표를 돌려준다 (속보가 필요 없음).

믿음 정도:
  낮음 = 비율이 달마다 25% 넘게 흔들리거나, 16개국 합이 전세계보다 큼 (짝이 안 맞음)
  보통 = 검색어가 1개뿐 (구글이 계단 값으로 반올림 → 0% / ±18% 로만 움직임) 또는 흔들림 15~25%
  높음 = 그 외
"""
import numpy as np
import pandas as pd


def combined(a, g=None):
    """본 데이터(a) 뒤에 구글애즈 파일(g)의 '더 새로운 달' 을 이어 붙인 월별 시리즈. 차트용.

    본 데이터에 이미 있는 (나라·브랜드·검색어) 조합만 붙인다 — 본 데이터에 빠진 검색어(인도
    'madeca cream' 등)를 최신 달에만 끼우면 그 달만 튀는 가짜 점프가 생긴다 (2026-10-15 확인).
    source 열: 'labs'(본) / 'gads'(구글애즈). 본 데이터가 따라잡으면 붙일 게 없어 그대로 돌려준다."""
    if a is None:
        return None
    a = a.copy()
    a["source"] = "labs"
    if g is None or not len(g):
        return a
    c = a[a["geo"] != "WW"]
    c_last = c.groupby(["geo", "keyword"])["month"].max().min()
    keys = set(zip(c["geo"], c["brand"], c["keyword"]))
    have = set(zip(c["geo"], c["brand"], c["keyword"], c["month"]))
    # (1) 본 데이터보다 새 달 전부 + (2) 본 데이터가 '일부 행만' 받은 달의 빈 칸 (DataForSEO 가 9월치를
    # 나라·검색어별로 띄엄띄엄 올리는 것을 2026-10-22 확인: 294행 중 233행만 9월이 있었음)
    add = g[(g["month"] >= c_last) & (g["geo"] != "WW")]
    add = add[[(k[:3] in keys) and (k not in have)
               for k in zip(add["geo"], add["brand"], add["keyword"], add["month"])]].copy()
    if not len(add):
        return a
    add["source"] = "gads"
    return pd.concat([a, add[a.columns]], ignore_index=True)


def nowcast(a, g=None):
    """a = absvol_monthly.csv DataFrame · g = absvol_gads.csv DataFrame (있으면).
    반환: 브랜드별 속보 표 (없으면 빈 DataFrame).

    g 가 본 데이터보다 새 달을 16개국 전부 갖고 있으면 그 **실측값**을 쓴다 (trust='실측').
    없으면 전세계(WW) 비율 추정으로 내려간다. 2026-10-15 확인: 구글애즈 엔드포인트와 본 데이터는
    같은 달에 미국 19개 브랜드 100% 같은 값 — 같은 출처."""
    cols = ["brand", "month", "ww_prev", "ww_now", "ww_mom", "ratio", "ratio_cv",
            "c16_prev", "c16_est", "c16_mom_est", "n_kw", "trust", "why"]
    if a is None:
        return pd.DataFrame(columns=cols)
    a = a[a["searches"] < 1_000_000]                       # tirtir 키워드 이상치 (funnel 과 같은 처리)
    c = a[a["geo"] != "WW"]
    c_last = c.groupby(["geo", "keyword"])["month"].max().min()   # 모든 나라·검색어가 가진 마지막 달
    geos16 = set(c["geo"])

    # ---- 1순위: 구글애즈 나라별 실측 (absvol_gads.csv)
    if g is not None and len(g):
        g = g[(g["geo"] != "WW") & (g["searches"] < 1_000_000)]
        g_last = g["month"].max()
        if g_last > c_last and geos16 <= set(g[g["month"] == g_last]["geo"]):
            cur = g[(g["month"] == g_last) & (g["geo"].isin(geos16))].groupby("brand")["searches"].sum()
            # 전월도 같은 구글애즈 파일에서 — 본 데이터는 일부 나라에서 검색어 행이 빠져 있어(인도 'madeca cream'
            # 등) 거기서 전월을 가져오면 범위가 달라 가짜 +41% 가 난다 (2026-10-15 확인).
            gp = g[(g["month"] == c_last) & (g["geo"].isin(geos16))].groupby("brand")["searches"].sum()
            prev = gp if len(gp) else c[c["month"] == c_last].groupby("brand")["searches"].sum()
            nkw = g[g["geo"] == "US"].groupby("brand")["keyword"].nunique()
            # 본 데이터가 그 달을 '일부 행만' 받은 상태면(DataForSEO 가 띄엄띄엄 올림) 문구를 바꿔 준다
            partial = c["month"].max() == g_last
            n_missing = int(len(set(zip(c["geo"], c["keyword"]))) - (c["month"] == g_last).sum()) if partial else 0
            why = (f"본 데이터 {g_last} 수신 · 아직 빈 {n_missing}행(나라×검색어)만 구글애즈로 보완 — 같은 출처"
                   if partial else "구글애즈 나라별 실측값 (16개국 합) — 본 데이터와 같은 출처")
            rows = []
            for b in cur.index:
                if b not in prev.index or prev[b] <= 0:
                    continue
                rows.append({"brand": b, "month": g_last, "ww_prev": np.nan, "ww_now": np.nan, "ww_mom": np.nan,
                             "ratio": 1.0, "ratio_cv": 0.0, "c16_prev": prev[b], "c16_est": cur[b],
                             "c16_mom_est": cur[b] / prev[b] - 1, "n_kw": int(nkw.get(b, 1)),
                             "trust": "실측", "why": why})
            return pd.DataFrame(rows, columns=cols)

    # ---- 2순위: 전세계(WW) 비율 추정
    if "WW" not in set(a["geo"]):
        return pd.DataFrame(columns=cols)
    w = a[a["geo"] == "WW"]
    w_last = w["month"].max()
    if w_last <= c_last:
        return pd.DataFrame(columns=cols)
    ww = w.groupby(["brand", "month"])["searches"].sum().unstack()
    c16 = c[c["month"] <= c_last].groupby(["brand", "month"])["searches"].sum().unstack()
    nkw = w.groupby("brand")["keyword"].nunique()
    over = [m for m in ww.columns if m in c16.columns and m <= c_last]
    prev = c_last
    rows = []
    for b in ww.index:
        if b not in c16.index or prev not in ww.columns:
            continue
        r = (c16.loc[b, over] / ww.loc[b, over]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) < 6 or pd.isna(ww.loc[b, w_last]) or pd.isna(ww.loc[b, prev]):
            continue
        ratio = float(r.iloc[-3:].mean())
        cv = float(r.std() / r.mean())
        est = float(ww.loc[b, w_last]) * ratio
        n = int(nkw.get(b, 1))
        if cv > 0.25 or ratio > 1.2:
            trust, why = "낮음", ("16개국 합 > 전세계 (짝이 안 맞음)" if ratio > 1.2 else f"비율 흔들림 {cv:.0%}")
        elif n == 1 or cv > 0.15:
            trust, why = "보통", ("검색어 1개 → 구글 계단 값 (0% · ±18% 로만 움직임)" if n == 1
                                  else f"비율 흔들림 {cv:.0%}")
        else:
            trust, why = "높음", f"검색어 {n}개 합 · 흔들림 {cv:.0%}"
        rows.append({"brand": b, "month": w_last, "ww_prev": ww.loc[b, prev], "ww_now": ww.loc[b, w_last],
                     "ww_mom": ww.loc[b, w_last] / ww.loc[b, prev] - 1, "ratio": ratio, "ratio_cv": cv,
                     "c16_prev": c16.loc[b, prev], "c16_est": est,
                     "c16_mom_est": est / c16.loc[b, prev] - 1, "n_kw": n, "trust": trust, "why": why})
    return pd.DataFrame(rows, columns=cols)
