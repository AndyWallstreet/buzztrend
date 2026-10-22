# -*- coding: utf-8 -*-
"""YG 엔터테인먼트 (122870) 트래커 — 매출 축을 세 갈래로 나눠 본다.

책갈피(탭) 3개:
  📀 제품 매출   — 실물 앨범 판매량(Circle Chart) → 앨범 매출 추정
  🎤 콘서트 매출 — BIGBANG / BABYMONSTER 투어 트래커
  🎯 컨센서스 비트 — 2026E 컨센서스 추이 + 상반기 실적의 컨센서스 달성률

데이터: yg_album_export.py (앨범·컨센서스), yg_tour_export.py (투어),
       findb (DART 분기 실적).
"""
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from app_pages import yg_tour_common

DATA = Path(__file__).resolve().parent.parent / "data" / "yg"
FINDB = Path(__file__).resolve().parent.parent / "data" / "findb" / "financials.csv.gz"
TICKER = "A122870"
C_BAR, C_LINE, C_GOLD = "#2a78d6", "#eb6834", "#e8c15a"

st.set_page_config(page_title="YG 트래커", page_icon="🎵", layout="wide")

from app_pages import sector_nav  # noqa: E402
sector_nav.sidebar("ent")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h {
    font-size: 1.18rem; font-weight: 600; background: #2a4a73;
    border-left: 4px solid #2e7de9; border-radius: 4px;
    padding: 6px 12px; margin: 0.9rem 0 0.5rem 0;
}
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


YEAR_C = 2026

# 아티스트 고정 색 — BABYMONSTER=노랑(블핑 빨강과 구분), 두 표기(Ikon/iKON) 모두 등록
ARTIST_C = {"BLACKPINK": "#e8425a", "BABYMONSTER": "#f2c744",
            "TREASURE": "#2fa89a", "BIGBANG": "#e8722a",
            "WINNER": "#8ec9ff", "Ikon": "#4fb862", "iKON": "#4fb862",
            "2NE1": "#b06fc9", "AKMU": "#2a78d6"}


def artist_scale(names):
    names = [n for n in names if n in ARTIST_C]
    return alt.Scale(domain=names, range=[ARTIST_C[n] for n in names])


def _shade(hex_c, f):
    """#rrggbb 를 f<1이면 어둡게, f>1이면 밝게."""
    r, g, b = (int(hex_c[i:i + 2], 16) for i in (1, 3, 5))
    if f <= 1:
        r, g, b = int(r * f), int(g * f), int(b * f)
    else:
        r = int(r + (255 - r) * (f - 1))
        g = int(g + (255 - g) * (f - 1))
        b = int(b + (255 - b) * (f - 1))
    return f"#{r:02x}{g:02x}{b:02x}"


def album_scale(pairs):
    """[(표시, group), ...] -> 그룹 색 계열로 앨범별 색 스케일."""
    seen = {}
    domain, rng = [], []
    for disp, grp in pairs:
        base = ARTIST_C.get(grp, "#8894a6")
        i = seen.get(grp, 0)
        seen[grp] = i + 1
        domain.append(disp)
        rng.append(_shade(base, [1.0, 1.35, 0.7, 1.6, 0.5][i % 5]))
    return alt.Scale(domain=domain, range=rng)


@st.cache_data(show_spinner=False)
def load_circle(name, stamp):
    p = DATA / name
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(show_spinner=False)
def load_album(stamp):
    p = DATA / "album_sales.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return df[df["artist"] != "Sum"].copy()


def _append_fn(df, cols):
    """Quantiwise 시계열(df) 뒤에 FnGuide 스냅샷(consensus_fn.csv)의 더 새로운 날짜만 이어 붙인다."""
    p = DATA / "consensus_fn.csv"
    if df is None or not p.exists():
        return df
    fn = pd.read_csv(p, parse_dates=["date"])
    fn = fn[fn["date"] > df["date"].max()][["date", "src"] + [c for c in cols if c in fn.columns]]
    if not len(fn):
        return df
    df = df.copy()
    if "src" not in df.columns:
        df["src"] = "qw"
    return pd.concat([df, fn], ignore_index=True).sort_values("date").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_consensus(stamp):
    p = DATA / "consensus.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    return _append_fn(df, ["rev_eok", "op_eok"])


@st.cache_data(show_spinner=False)
def load_consensus_seg(stamp):
    p = DATA / "consensus_seg.csv"
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


@st.cache_data(show_spinner=False)
def load_actuals():
    if not FINDB.exists():
        return None
    f = pd.read_csv(FINDB)
    f = f[f["ticker"] == TICKER].sort_values("q")
    return f if len(f) else None


def _stamp(name):
    p = DATA / name
    return round(p.stat().st_mtime, 3) if p.exists() else 0.0


def _stamp2(*names):
    return tuple(_stamp(n) for n in names)


st.title("YG 엔터테인먼트 트래커")
st.caption("와이지엔터테인먼트 (122870) · 매출 3대 축 — 제품(앨범) · 콘서트 · "
           "컨센서스 대비 실적 | 출처: YG 분석 워크북 + DART")

tab_prod, tab_tour, tab_cons = st.tabs(
    ["📀 제품 매출 (앨범)", "🎤 콘서트 매출", "🎯 컨센서스 비트"])

# ------------------------------------------------------------------ 제품 매출
with tab_prod:
    # ---------------- 앨범 발매 캘린더 (수기: data/yg/album_schedule.csv) ----------------
    sch = load_circle("album_schedule.csv", _stamp("album_schedule.csv"))
    if sch is not None and len(sch):
        sub("앨범 발매 캘린더", "언제 · 누가 · 어떤 앨범 → 어느 분기 추정에 넣을지 · 점 = 발매 완료, 막대 = 예정 구간(날짜 미정)")
        sc = sch.copy()
        sc["start"] = pd.to_datetime(sc["start"])
        sc["end"] = pd.to_datetime(sc["end"])
        sc["done"] = sc["status"].eq("발매완료")
        sc["표시"] = sc["title"] + " (" + sc["type"] + ")"
        _today = pd.Timestamp.today().normalize()
        _cm = load_circle("yg_albums_monthly.csv", _stamp("yg_albums_monthly.csv"))

        def _first_month(key):
            """Circle 월간 기준 첫 달 판매·누적 (만장)."""
            if _cm is None or not isinstance(key, str) or not key:
                return None, None
            x = _cm[_cm["album"].astype(str).str.contains(key, regex=False)]
            if not len(x):
                return None, None
            bym = x.groupby("period")["sales"].sum().sort_index()
            return bym.iloc[0] / 1e4, bym.sum() / 1e4

        _fm = sc["circle_key"].map(_first_month)
        sc["첫 달 (만장)"] = [v[0] for v in _fm]
        sc["누적 (만장)"] = [v[1] for v in _fm]
        _grp_order = list(dict.fromkeys(sc.sort_values("start")["group"]))
        _x = alt.X("start:T", title=None, axis=alt.Axis(format="%y-%m", tickCount=14),
                   scale=alt.Scale(domain=[pd.Timestamp("2026-01-01"), pd.Timestamp("2027-06-30")], clamp=True))
        _tt = ["group", "title", "type", "date_label", "status", "apply_q", "note"]
        _stat_scale = alt.Scale(domain=["발매완료", "예정 · 날짜 미정", "미확정"],
                                range=["#3fb27f", "#f2c744", "#8a97aa"])
        pts = alt.Chart(sc[sc["done"]]).mark_point(filled=True, size=190, opacity=1).encode(
            x=_x, y=alt.Y("group:N", sort=_grp_order, title=None),
            color=alt.Color("status:N", title=None, scale=_stat_scale, legend=alt.Legend(orient="top")),
            shape=alt.Shape("physical:N", title="피지컬 앨범", scale=alt.Scale(domain=["Y", "N"], range=["circle", "diamond"]),
                            legend=alt.Legend(orient="top")),
            tooltip=_tt)
        win = alt.Chart(sc[~sc["done"]]).mark_bar(height=14, opacity=0.75, cornerRadius=3).encode(
            x=_x, x2="end:T", y=alt.Y("group:N", sort=_grp_order, title=None),
            color=alt.Color("status:N", title=None, scale=_stat_scale), tooltip=_tt)
        lab = alt.Chart(sc).mark_text(dy=-15, fontSize=10, color="#dde5f0", align="left").encode(
            x=_x, y=alt.Y("group:N", sort=_grp_order), text="title:N")
        now = alt.Chart(pd.DataFrame({"d": [_today]})).mark_rule(color="#e05252", strokeDash=[4, 3]).encode(x="d:T")
        st.altair_chart(alt.layer(win, pts, lab, now).properties(height=60 + 52 * len(_grp_order)),
                        use_container_width=True)
        show = sc.sort_values("start")[["date_label", "group", "title", "type", "physical", "status", "apply_q",
                                        "첫 달 (만장)", "누적 (만장)", "note", "source", "url"]].rename(columns={
            "date_label": "발매일", "group": "그룹", "title": "앨범", "type": "종류", "physical": "피지컬",
            "status": "상태", "apply_q": "추정 반영 분기", "note": "메모", "source": "출처", "url": "링크"})
        st.dataframe(show, hide_index=True, use_container_width=True,
                     column_config={"첫 달 (만장)": st.column_config.NumberColumn(format="%.1f"),
                                    "누적 (만장)": st.column_config.NumberColumn(format="%.1f"),
                                    "링크": st.column_config.LinkColumn(display_text="열기")})
        _d = sc[sc["done"] & sc["첫 달 (만장)"].notna() & (sc["누적 (만장)"] > 10)]
        _share = (_d["첫 달 (만장)"].sum() / _d["누적 (만장)"].sum()) if len(_d) else None
        st.caption("**추정에 넣는 법**: Circle은 출하 기준이라 선주문 물량이 **발매 달에 한꺼번에** 잡힘"
                   + (f" — 2026년 주요 3개 앨범은 누적의 {_share:.0%}가 첫 달." if _share else ".")
                   + " → 앨범 판매는 **발매일이 속한 분기**에 넣을 것. 월말 발매면 일부가 다음 달로 넘어감. "
                     "디지털 싱글(◆)은 판매량 없음. 빨간 점선 = 오늘. 노랑·회색 막대는 공식 날짜가 없어 구간으로 표시 — "
                   f"확정 공지가 나오면 album_schedule.csv 를 고칠 것 (마지막 확인 {sc['checked'].max()}).")
        st.divider()

    alb = load_album(_stamp("album_sales.csv"))
    if alb is None or not len(alb):
        st.info("앨범 데이터가 없습니다 — `python yg_album_export.py` 를 먼저 실행하세요.")
    else:
        c1, c2 = st.columns([1, 3], gap="large")
        with c1:
            y_min, y_max = int(alb["year"].min()), int(alb["year"].max())
            y0, y1 = st.slider("기간", y_min, y_max, (max(y_min, y_max - 10), y_max),
                               key="yg_alb_yr")
            asp = st.number_input("앨범 ASP (원/장)", 5000, 60000, 30000, 1000,
                                  key="yg_asp",
                                  help="워크북 Album 시트 가정 기본값 30,000원. "
                                       "앨범 매출 = 판매량 × ASP")
        a = alb[(alb["year"] >= y0) & (alb["year"] <= y1)].copy()
        a["장수(만장)"] = a["copies"] / 1e4
        by_year = a.groupby("year", as_index=False).agg(
            copies=("copies", "sum"), est=("is_est", "max"))
        by_year["매출추정(억)"] = by_year["copies"] * asp / 1e8

        # 요약 지표 — 최근 실적 연도 기준
        act = by_year[~by_year["est"]]
        with c2:
            if len(act):
                last = act.iloc[-1]
                prev = act.iloc[-2] if len(act) >= 2 else None
                m1, m2, m3 = st.columns(3)
                m1.metric(f"{int(last['year'])}년 앨범 판매",
                          f"{last['copies'] / 1e4:,.0f}만장",
                          f"{(last['copies'] / prev['copies'] - 1) * 100:+.0f}% YoY"
                          if prev is not None and prev["copies"] else None)
                m2.metric(f"{int(last['year'])}년 앨범 매출 추정",
                          f"{last['copies'] * asp / 1e8:,.0f}억원",
                          f"ASP {asp:,}원 가정", delta_color="off")
                _top = (a[a["year"] == last["year"]]
                        .sort_values("copies", ascending=False))
                if len(_top):
                    m3.metric("최다 판매 아티스트", _top.iloc[0]["artist"],
                              f"{_top.iloc[0]['copies'] / 1e4:,.0f}만장",
                              delta_color="off")

        sub("연도별 앨범 판매량", "아티스트별 누적 · Circle Chart 집계 (E = 추정)")
        a["연도"] = a["year"].astype(str) + np.where(a["is_est"], "E", "")
        bars = alt.Chart(a).mark_bar(opacity=0.9).encode(
            x=alt.X("연도:N", sort=None, title=None),
            y=alt.Y("장수(만장):Q", title="앨범 판매 (만장)", stack=True),
            color=alt.Color("artist:N", title="아티스트",
                            scale=artist_scale(sorted(a["artist"].unique())),
                            legend=alt.Legend(orient="top", columns=5)),
            tooltip=["연도", "artist",
                     alt.Tooltip("장수(만장)", format=",.1f")])
        _tot = a.groupby("연도", as_index=False)["장수(만장)"].sum()
        labels = alt.Chart(_tot).mark_text(dy=-8, color="#dde5f0",
                                           fontSize=11).encode(
            x=alt.X("연도:N", sort=None),
            y=alt.Y("장수(만장):Q"),
            text=alt.Text("장수(만장):Q", format=",.0f"))
        st.altair_chart(alt.layer(bars, labels).properties(height=380),
                        use_container_width=True)

        sub("앨범 매출 추정", f"판매량 × ASP {asp:,}원")
        by_year["연도"] = (by_year["year"].astype(str)
                          + np.where(by_year["est"], "E", ""))
        rev_bars = alt.Chart(by_year).mark_bar(opacity=0.9).encode(
            x=alt.X("연도:N", sort=None, title=None),
            y=alt.Y("매출추정(억):Q", title="앨범 매출 추정 (억원)"),
            color=alt.Color("est:N", title=None,
                            scale=alt.Scale(domain=[False, True],
                                            range=[C_BAR, C_LINE]),
                            legend=alt.Legend(orient="top",
                                              labelExpr="datum.label == 'true' "
                                                        "? '추정' : '실적'")),
            tooltip=["연도", alt.Tooltip("매출추정(억)", format=",.0f"),
                     alt.Tooltip("copies", format=",.0f", title="판매량(장)")])
        rev_lab = alt.Chart(by_year).mark_text(dy=-8, color="#dde5f0",
                                               fontSize=11).encode(
            x=alt.X("연도:N", sort=None),
            y=alt.Y("매출추정(억):Q"),
            text=alt.Text("매출추정(억):Q", format=",.0f"))
        st.altair_chart(alt.layer(rev_bars, rev_lab).properties(height=300),
                        use_container_width=True)
        st.caption("실물 앨범 판매량은 Circle Chart(구 가온) 집계 기준이며, 워크북 "
                   "Album 시트에서 가져옵니다. 매출 추정은 단순히 판매량 × ASP라 "
                   "실제 제품 매출(음원·MD 포함)과는 다릅니다.")

    # ---------------- 앨범별 상세 (Circle Chart 자동 수집) ----------------
    st.divider()
    sub("앨범별 상세 — Circle Chart 자동 수집",
        "집계 계단: 주간(잠정) → 월간(확정) → 분기·반기 → 연간 · 출하량-반품량 기준")
    cm = load_circle("yg_albums_monthly.csv", _stamp("yg_albums_monthly.csv"))
    cw = load_circle("yg_albums_weekly.csv", _stamp("yg_albums_weekly.csv"))
    if cm is None or not len(cm):
        st.info("Circle 데이터가 없습니다 — python yg_circle_update.py 를 실행하세요.")
    else:
        cm = cm.copy()
        cm["sales"] = cm["sales"].astype(float)
        cm["_m"] = cm["period"].str[5:7].astype(int)
        last_pub_m = int(cm["_m"].max())          # 월간 차트가 발표된 마지막 달

        # 주간 → 잠정 월 합산 (월간 미발표 달만)
        wk = None
        if cw is not None and len(cw):
            wk = cw.copy()
            wk["sales"] = wk["sales"].astype(float)
            wk["start"] = pd.to_datetime(wk["start"])
            # 귀속 월 = 주 중간일(수요일) 기준 — 시작일 기준이면 8/30~9/5 주가 8월로 가서
            # (8월은 월간 확정이라) 통째로 빠짐. 2026-09-21 수정.
            wk["_m"] = (wk["start"] + pd.Timedelta(days=3)).dt.month
        pend = (wk[wk["_m"] > last_pub_m] if wk is not None else None)

        # ---- 요약 지표: 반기 → 연간 계단
        h1 = cm[cm["_m"] <= 6]["sales"].sum()
        h2_pub = cm[cm["_m"] > 6]["sales"].sum()
        h2_pend = pend["sales"].sum() if pend is not None else 0
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("상반기(1H) 확정", f"{h1 / 1e4:,.0f}만장", "월간 차트 1~6월 합",
                  delta_color="off")
        s2.metric("하반기(2H) 진행", f"{(h2_pub + h2_pend) / 1e4:,.1f}만장",
                  f"월간 {h2_pub / 1e4:,.1f} + 주간 잠정 {h2_pend / 1e4:,.1f}",
                  delta_color="off")
        s3.metric("연간 누적 (잠정)", f"{(h1 + h2_pub + h2_pend) / 1e4:,.0f}만장",
                  "확정 월간 + 잠정 주간", delta_color="off")
        if wk is not None and len(wk):
            _lw = wk[wk["week"].astype(int) == wk["week"].astype(int).max()]
            s4.metric(f"최근 주간 (W{int(_lw['week'].iloc[0])})",
                      f"{_lw['sales'].sum():,.0f}장",
                      f"{_lw['end'].iloc[0]} 마감", delta_color="off")

        # ---- 월별 판매 (그룹 스택) — 진행 중인 달은 주간 잠정 합산으로 채움
        mon = cm.groupby(["_m", "group"], as_index=False)["sales"].sum()
        mon["월"] = mon["_m"].astype(str) + "월"
        if pend is not None and len(pend):
            pm = pend.groupby(["_m", "group"], as_index=False)["sales"].sum()
            pm["월"] = pm["_m"].astype(str) + "월*"
            mon = pd.concat([mon, pm], ignore_index=True)
        mon["만장"] = mon["sales"] / 1e4
        _morder = ([f"{m}월" for m in range(1, 13)]
                   + [f"{m}월*" for m in range(1, 13)])
        mon["_ord"] = mon["월"].map({v: i for i, v in enumerate(_morder)})
        mon = mon.sort_values("_ord")
        _mx = list(dict.fromkeys(mon["월"]))
        g1, g2 = st.columns(2, gap="large")
        with g1:
            bars = alt.Chart(mon).mark_bar(opacity=0.9).encode(
                x=alt.X("월:N", sort=_mx, title=None),
                y=alt.Y("만장:Q", title="월 판매 (만장)", stack=True),
                color=alt.Color("group:N", title=None,
                                scale=artist_scale(sorted(mon["group"].unique())),
                                legend=alt.Legend(orient="top")),
                tooltip=["월", "group", alt.Tooltip("만장", format=",.1f")])
            _mt = mon.groupby("월", as_index=False)["만장"].sum()
            lab = alt.Chart(_mt).mark_text(dy=-8, color="#dde5f0",
                                           fontSize=10).encode(
                x=alt.X("월:N", sort=_mx),
                y="만장:Q", text=alt.Text("만장:Q", format=",.1f"))
            st.altair_chart(alt.layer(bars, lab).properties(height=300),
                            use_container_width=True)
            st.caption("**읽는법**: 그룹별 월 판매. 별표(*) 달 = 월간 차트 미발표라 "
                       "주간 차트 잠정 합산 — Circle이 월간을 발표하면 자동으로 확정치로 "
                       "바뀜(주간→월간 계단). 컴백 달에 막대가 서는 게 정상.")
        with g2:
            qq = cm.copy()
            qq["분기"] = "Q" + ((qq["_m"] - 1) // 3 + 1).astype(str)
            qg = qq.groupby(["분기", "group"], as_index=False)["sales"].sum()
            qg["구분"] = "확정(월간)"
            if pend is not None and len(pend):      # 월간 미발표 달 = 주간 잠정치를 옅게 얹음
                pq = pend.copy()
                pq["분기"] = "Q" + ((pq["_m"] - 1) // 3 + 1).astype(str)
                pq = pq.groupby(["분기", "group"], as_index=False)["sales"].sum()
                pq["구분"] = "잠정(주간)"
                qg = pd.concat([qg, pq], ignore_index=True)
            qg["만장"] = qg["sales"] / 1e4
            bars = alt.Chart(qg).mark_bar().encode(
                opacity=alt.Opacity("구분:N", title=None,
                                    scale=alt.Scale(domain=["확정(월간)", "잠정(주간)"], range=[0.92, 0.45]),
                                    legend=alt.Legend(orient="top")),
                order=alt.Order("구분:N"),
                x=alt.X("분기:N", title=None,
                        scale=alt.Scale(domain=["Q1", "Q2", "Q3", "Q4"])),
                y=alt.Y("만장:Q", title="분기 판매 (만장)", stack=True),
                color=alt.Color("group:N", title=None,
                                scale=artist_scale(sorted(qg["group"].unique())),
                                legend=alt.Legend(orient="top")),
                tooltip=["분기", "구분", "group", alt.Tooltip("만장", format=",.1f")])
            _qt = qg.groupby("분기", as_index=False)["만장"].sum()
            lab = alt.Chart(_qt).mark_text(dy=-8, color="#dde5f0",
                                           fontSize=11).encode(
                x=alt.X("분기:N",
                        scale=alt.Scale(domain=["Q1", "Q2", "Q3", "Q4"])),
                y="만장:Q", text=alt.Text("만장:Q", format=",.1f"))
            st.altair_chart(alt.layer(bars, lab).properties(height=300),
                            use_container_width=True)
            st.caption(f"**읽는법**: 진한 색 = 확정 월간({last_pub_m}월까지), 옅은 색 = 월간 미발표 달의 "
                       "주간 차트 잠정 합산. 진행 중 분기는 미완성 — 월간이 발표되면 옅은 부분이 확정치로 바뀜. "
                       "Circle은 톱100만 공개라 순위 밖 구작 판매는 빠짐(월 100위 컷 약 0.5만장) → 실제보다 조금 낮음.")

        # ---- 주간 상세 (최근 펄스) — 그룹 라벨 + 상위 5개만
        if wk is not None and len(wk):
            sub("주간 판매 펄스", "최근 주간 차트 · 상위 5개 앨범 · 이름 앞 = 그룹")
            wk2 = wk.copy()
            wk2["표시"] = wk2["group"] + " · " + wk2["album"].str.slice(0, 22)
            top5 = (wk2.groupby("표시")["sales"].sum()
                    .sort_values(ascending=False).head(5).index)
            ww = wk2[wk2["표시"].isin(top5)]
            _pairs = (ww[["표시", "group"]].drop_duplicates()
                      .sort_values(["group", "표시"]).values.tolist())
            ch = alt.Chart(ww).mark_line(
                size=3, point=alt.OverlayMarkDef(size=70)).encode(
                x=alt.X("start:T", title=None,
                        axis=alt.Axis(format="%m/%d", tickCount=10)),
                y=alt.Y("sales:Q", title="주간 판매 (장)"),
                color=alt.Color("표시:N", title=None,
                                scale=album_scale(_pairs),
                                legend=alt.Legend(orient="top", columns=2,
                                                  labelLimit=260)),
                tooltip=["표시", alt.Tooltip("start:T", title="주 시작"),
                         alt.Tooltip("sales", format=",.0f")])
            wlab = alt.Chart(ww).mark_text(dy=-11, fontSize=9,
                                           color="#c9d4e4").encode(
                x="start:T", y="sales:Q",
                text=alt.Text("sales:Q", format=",.0f"),
                detail="표시:N")
            st.altair_chart(alt.layer(ch, wlab).properties(height=320),
                            use_container_width=True)
            st.caption("**읽는법**: 주간 차트 그대로의 최신 펄스 — 월간 발표 전의 "
                       "선행 지표(위 월별 차트의 별표 달을 만드는 재료). 발매 첫 주 "
                       "초동 후 급감이 정상, 2주차 잔존율이 높으면 팬덤 확장 신호. "
                       "톱100 밖으로 밀리면 선이 끊김. 점 위 숫자 = 해당 주 판매량.")

        # ---- 그룹별 합산 표 (그룹 합계 행 + 소속 앨범 행)
        sub("그룹 → 앨범 누적 표", f"{YEAR_C}년 · 확정 월간 + 잠정 주간(미발표 달) 합산")
        alb_tot = cm.groupby(["group", "album"], as_index=False).agg(
            누적=("sales", "sum"))
        if pend is not None and len(pend):
            pt = pend.groupby(["group", "album"], as_index=False).agg(
                잠정=("sales", "sum"))
            alb_tot = alb_tot.merge(pt, on=["group", "album"], how="outer")
        else:
            alb_tot["잠정"] = 0.0
        alb_tot[["누적", "잠정"]] = alb_tot[["누적", "잠정"]].fillna(0)
        alb_tot["합계"] = alb_tot["누적"] + alb_tot["잠정"]
        _lwm = {}
        if wk is not None and len(wk):
            _lw = wk[wk["week"].astype(int) == wk["week"].astype(int).max()]
            _lwm = dict(zip(_lw["group"] + "|" + _lw["album"],
                            _lw["sales"].astype(float)))
        rows = []
        gtot = (alb_tot.groupby("group")["합계"].sum()
                .sort_values(ascending=False))
        for grp, gv in gtot.items():
            rows.append({"그룹/앨범": f"■ {grp} — 합계", "연간 누적(장)": gv,
                         "최근 주간(장)": sum(v for k, v in _lwm.items()
                                          if k.startswith(grp + "|"))})
            sub_df = (alb_tot[alb_tot["group"] == grp]
                      .sort_values("합계", ascending=False))
            for _, r_ in sub_df.iterrows():
                rows.append({"그룹/앨범": "      └ " + r_["album"],
                             "연간 누적(장)": r_["합계"],
                             "최근 주간(장)": _lwm.get(grp + "|" + r_["album"])})
        tdf = pd.DataFrame(rows)
        tdf["연간 누적(장)"] = tdf["연간 누적(장)"].map(
            lambda v: f"{v:,.0f}" if pd.notna(v) and v else "—")
        tdf["최근 주간(장)"] = tdf["최근 주간(장)"].map(
            lambda v: f"{v:,.0f}" if pd.notna(v) and v else "—")
        def _hl(row):
            if str(row["그룹/앨범"]).startswith("■"):
                return ["background-color: #1e3a5c; color: #f2c744; "
                        "font-weight: 700"] * len(row)
            return [""] * len(row)
        st.dataframe(tdf.style.apply(_hl, axis=1), hide_index=True,
                     use_container_width=True,
                     height=min(80 + 36 * len(tdf), 480))
        st.caption("**읽는법**: ■ = 그룹 합계(모든 앨범·버전 포함), └ = 개별 앨범/버전. "
                   "누적은 톱100 안에 든 기간만 합산이라 롱테일은 빠짐(과소집계). "
                   "매일 배치가 주간 차트를 자동 반영하고, 월간 발표 시 잠정치가 "
                   "확정치로 대체됨.")

# ------------------------------------------------------------------ 콘서트
with tab_tour:
    _cfg = {"BIGBANG": ("bigbang_tour.csv", "bigbang_booking.csv"),
            "BABYMONSTER": ("babymonster_tour.csv", "babymonster_booking.csv"),
            "TREASURE": ("treasure_tour.csv", "treasure_booking.csv"),
            "BLACKPINK": ("blackpink_tour.csv", "blackpink_booking.csv")}
    _avail = [a for a, (tc, _bc0) in _cfg.items() if (DATA / tc).exists()]
    artist = st.radio("아티스트", _avail, horizontal=True,
                      key="yg_tour_artist")
    _tc, _bc = _cfg[artist]
    yg_tour_common.render(artist=artist, tour_csv=_tc, booking_csv=_bc,
                          ticker_note="종목: 와이지엔터테인먼트 (122870)")

# ------------------------------------------------------------------ 컨센서스
with tab_cons:
    cons = load_consensus(_stamp2("consensus.csv", "consensus_fn.csv"))
    act = load_actuals()
    if cons is None or not len(cons):
        st.info("컨센서스 데이터가 없습니다 — `python yg_album_export.py` 를 "
                "먼저 실행하세요.")
    else:
        cur = cons.iloc[-1]
        first = cons.iloc[0]
        _m3 = cons[cons["date"] >= cur["date"] - pd.Timedelta(days=90)].iloc[0]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("2026E 매출 컨센서스", f"{cur['rev_eok']:,.0f}억원",
                  f"3개월 {cur['rev_eok'] / _m3['rev_eok'] * 100 - 100:+.1f}%")
        m2.metric("2026E 영업이익 컨센서스", f"{cur['op_eok']:,.0f}억원",
                  f"3개월 {cur['op_eok'] / _m3['op_eok'] * 100 - 100:+.1f}%"
                  if _m3["op_eok"] else None)
        m3.metric("2026E 영업이익률", f"{cur['op_eok'] / cur['rev_eok'] * 100:.1f}%")
        if "n_rev" in cons.columns and pd.notna(cur.get("n_rev")):
            m4.metric("참여 증권사", f"{int(cur['n_rev'])}곳",
                      f"1년 전 {int(first['n_rev'])}곳"
                      if pd.notna(first.get("n_rev")) else None,
                      delta_color="off")
        else:
            m4.metric("컨센서스 기준일", str(cur["date"])[:10],
                      "FnGuide (매일 수집)" if str(cur.get("src", "qw")).startswith("fn")
                      else "콴티와이즈 일별", delta_color="off")

        sub("컨센서스 추이", "1년간 2026년 연간 추정치가 어떻게 바뀌었나 "
                         "(올라가면 실적이 기대를 넘고 있다는 뜻)")
        cm = cons.melt("date", value_vars=["rev_eok", "op_eok"],
                       var_name="구분", value_name="억원")
        cm["구분"] = cm["구분"].map({"rev_eok": "매출 2026E",
                                   "op_eok": "영업이익 2026E"})
        base = alt.Chart(cm).encode(x=alt.X("date:T", title=None))
        rev_l = base.transform_filter(alt.datum.구분 == "매출 2026E").mark_line(
            color=C_BAR, size=2.5).encode(
            y=alt.Y("억원:Q", title="매출 컨센서스 (억원)",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="날짜"),
                     alt.Tooltip("억원", format=",.0f", title="매출 2026E")])
        op_l = base.transform_filter(alt.datum.구분 == "영업이익 2026E").mark_line(
            color=C_GOLD, size=2.5).encode(
            y=alt.Y("억원:Q", title="영업이익 컨센서스 (억원)",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="날짜"),
                     alt.Tooltip("억원", format=",.0f", title="영업이익 2026E")])
        st.altair_chart(alt.layer(rev_l, op_l).resolve_scale(y="independent")
                        .properties(height=340).interactive(),
                        use_container_width=True)
        _qw_last = cons[cons.get("src", pd.Series("qw", index=cons.index)) == "qw"]["date"].max() if "src" in cons.columns else cons["date"].max()
        st.caption("파랑 = 매출(왼쪽 축), 금색 = 영업이익(오른쪽 축). "
                   f"출처: 워크북 vs CONSENSUS 시트(Quantiwise 일별, ~{str(_qw_last)[:10]}) + "
                   "그 뒤는 FnGuide 컨센서스를 매일 한 점씩 수집(yg_consensus_fn.py). "
                   "두 소스는 표본이 달라 이음새에서 값이 살짝 튈 수 있음.")

        # ---- 분기 컨센서스 vs 워크북 바텀업 (투어+앨범)
        cq = load_circle("consensus_q.csv", _stamp("consensus_q.csv"))
        if cq is not None and len(cq):
            cq = cq.copy(); cq["date"] = pd.to_datetime(cq["date"])
            cq = _append_fn(cq, ["rev3q_eok", "op3q_eok", "rev4q_eok", "op4q_eok"])
            cq["date"] = cq["date"].dt.strftime("%Y-%m-%d")
        tq = load_circle("tour_quarterly.csv", _stamp("tour_quarterly.csv"))
        aq = load_circle("album_quarterly.csv", _stamp("album_quarterly.csv"))
        if cq is not None and len(cq) and tq is not None and aq is not None:
            sub("분기 컨센서스 vs 내 베이스 추정 (3Q·4Q)",
                "컨센서스(콴티와이즈 → 9/7 이후 FnGuide) ↔ 워크북 바텀업: 투어(Tour_Quarterly) + "
                "앨범(Album_Quarterly), Base 시나리오")
            _cql = cq.iloc[-1]
            rows_c = []
            for _qn, _rk, _ok in (("2026 3Q", "rev3q_eok", "op3q_eok"),
                                  ("2026 4Q", "rev4q_eok", "op4q_eok")):
                _t = tq[tq["quarter"] == _qn]
                _a = aq[aq["quarter"] == _qn]
                tour_eok = float(_t["total_mn"].iloc[0]) / 100 if len(_t) else 0
                alb_eok = float(_a["yg_rev_mn"].iloc[0]) / 100 if len(_a) else 0
                cons_rev = float(_cql.get(_rk)) if pd.notna(_cql.get(_rk)) else None
                cons_op = float(_cql.get(_ok)) if pd.notna(_cql.get(_ok)) else None
                covered = tour_eok + alb_eok
                rows_c.append({
                    "분기": _qn.replace("2026 ", "") + "26",
                    "컨센 매출(억)": f"{cons_rev:,.0f}" if cons_rev else "—",
                    "투어(억)": f"{tour_eok:,.0f}",
                    "앨범(억)": f"{alb_eok:,.0f}",
                    "투어+앨범(억)": f"{covered:,.0f}",
                    "커버리지": (f"{covered / cons_rev * 100:.0f}%"
                                if cons_rev else "—"),
                    "나머지 필요(억)": (f"{cons_rev - covered:,.0f}"
                                    if cons_rev else "—"),
                    "컨센 영업이익(억)": f"{cons_op:,.0f}" if cons_op else "—",
                })
            st.dataframe(pd.DataFrame(rows_c), hide_index=True,
                         use_container_width=True)
            st.caption("**읽는법**: '나머지 필요'는 음원·유튜브·MD·출연료 등 투어·앨범 "
                       "외 매출이 채워야 하는 몫 — YG의 기타 매출은 분기당 대략 "
                       "1,000억 안팎이므로 이 값이 그 근처면 컨센서스는 달성 가능 "
                       "범위, 크게 위면 컨센 상향(비트) 여지, 아래면 하향 위험. "
                       f"컨센서스 기준일 {_cql['date']}. 투어·앨범 수치는 워크북 "
                       "Base 시나리오 계산값(2026 3Q 투어 674억·4Q 711억).")

        # ---- 상반기 실적의 컨센서스 달성률
        if act is not None:
            yr = int(cons["date"].iloc[-1].year)
            ytd = act[act["q"].str.startswith(str(yr))]
            if len(ytd):
                sub("올해 실적 진행률", f"{yr}년 누적 실적이 연간 컨센서스의 몇 %인가")
                r_ytd = ytd["rev"].sum() / 1e8
                o_ytd = ytd["ebit"].sum() / 1e8
                nq = len(ytd)
                p1, p2, p3 = st.columns(3)
                p1.metric(f"{yr}년 누적 매출 ({nq}개 분기)", f"{r_ytd:,.0f}억원",
                          f"컨센서스의 {r_ytd / cur['rev_eok'] * 100:.0f}%",
                          delta_color="off")
                p2.metric(f"{yr}년 누적 영업이익", f"{o_ytd:,.0f}억원",
                          f"컨센서스의 {o_ytd / cur['op_eok'] * 100:.0f}%"
                          if cur["op_eok"] else None, delta_color="off")
                _pace = nq / 4 * 100
                p3.metric("단순 진도 기준", f"{_pace:.0f}%",
                          "이보다 높으면 초과 달성 페이스", delta_color="off")
                _gap = r_ytd / cur["rev_eok"] * 100 - _pace
                if _gap >= 3:
                    st.success(f"매출이 단순 진도({_pace:.0f}%)보다 "
                               f"**{_gap:+.0f}%p** 앞서 있습니다 — 컨센서스 상향 "
                               "여지가 있는 구간.")
                elif _gap <= -3:
                    st.warning(f"매출이 단순 진도({_pace:.0f}%)보다 "
                               f"**{_gap:+.0f}%p** 뒤쳐져 있습니다 — 하반기에 "
                               "몰아쳐야 컨센서스를 맞춥니다.")
                else:
                    st.info(f"매출이 단순 진도({_pace:.0f}%)와 비슷한 속도입니다.")
                st.caption("실적 = DART 분기보고서(연결) 누적, 컨센서스 = 위 차트의 "
                           "최신값. 엔터는 앨범 발매·투어 일정에 따라 분기 편차가 커서 "
                           "단순 진도(분기수÷4)와의 비교는 참고용입니다.")

        # ---- 증권사별 컨센서스 vs 우리 뷰 (워크북 Consensus_Seg 시트와 같은 데이터)
        seg = load_consensus_seg(_stamp("consensus_seg.csv"))
        if seg is not None and len(seg):
            import json as _json
            _mp = DATA / "model_segments.json"
            model = _json.loads(_mp.read_text(encoding="utf-8")) if _mp.exists() else {}
            sub("증권사별 컨센서스 vs 우리 뷰 — 어디서 컨센을 이길 수 있나",
                f"증권사 {seg['broker'].nunique()}곳 최신 리포트의 부문별 추정 (워크북 Consensus_Seg, "
                f"{seg['date'].max()} 기준) ↔ 우리 모델 Base")
            s26 = seg[seg["fy"] == "2026E"].copy()
            s26["상제품"] = s26[["음반", "음원", "MD"]].sum(axis=1, min_count=3)
            m26 = model.get("2026E", {})
            rows_v = []
            for lab, col, mkey in (("상·제품 (음반+음원+MD)", "상제품", "상제품"), ("  └ MD만", "MD", "MD라이선싱"),
                                   ("콘서트", "콘서트", "콘서트"), ("음악서비스", "음악서비스", "음악서비스"),
                                   ("광고", "광고", "광고"), ("로열티", "로열티", "로열티"),
                                   ("출연료", "출연료", "출연료"), ("기타", "기타", "기타"), ("매출 합계", "rev", "매출")):
                v = pd.to_numeric(s26[col], errors="coerce").dropna()
                mv = m26.get(mkey)
                rows_v.append({"부문": lab, "컨센 평균(십억)": round(v.mean(), 1) if len(v) else None,
                               "컨센 최저~최고": f"{v.min():.0f}~{v.max():.0f}" if len(v) else "—",
                               "우리 모델(십억)": mv,
                               "차이(십억)": round(mv - v.mean(), 1) if (mv is not None and len(v)) else None,
                               "차이(%)": f"{(mv / v.mean() - 1) * 100:+.0f}%" if (mv is not None and len(v)) else "—"})
            st.dataframe(pd.DataFrame(rows_v), hide_index=True, use_container_width=True)
            st.caption("단위 십억원(KRWbn). 우리 모델의 MD는 '라이선싱 포함'이라 증권사 MD보다 정의가 넓음. "
                       "2027E는 우리 모델이 미완성(투어·앨범 일정 미입력)이라 비교하지 않음.")

            # 3Q26E 프리뷰 비교
            q = seg[seg["fy"] == "3Q26E"].copy()
            if len(q):
                _t = tq[tq["quarter"] == "2026 3Q"] if tq is not None else None
                _a = aq[aq["quarter"] == "2026 3Q"] if aq is not None else None
                tour3 = float(_t["total_mn"].iloc[0]) / 1000 if _t is not None and len(_t) else None
                alb3 = float(_a["yg_rev_mn"].iloc[0]) / 1000 if _a is not None and len(_a) else None
                fn = None
                _fp = DATA / "consensus_fn.csv"
                if _fp.exists():
                    _f = pd.read_csv(_fp); fn = _f.iloc[-1]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("3Q26E 매출 · 증권사 범위", f"{q['rev'].min():.0f}~{q['rev'].max():.0f}십억",
                          f"평균 {q['rev'].mean():.1f} (3Q25 실적 173.1)", delta_color="off")
                c2.metric("3Q26E 영업이익 · 증권사 범위", f"{q['op'].min():.0f}~{q['op'].max():.0f}십억",
                          f"평균 {q['op'].mean():.1f} (3Q25 실적 31.1)", delta_color="off")
                if fn is not None:
                    c3.metric("FnGuide 3Q26 컨센", f"{fn['rev3q_eok'] / 10:.1f} / {fn['op3q_eok'] / 10:.1f}십억",
                              f"{fn['date']} 매출/영업이익", delta_color="off")
                if tour3 is not None:
                    c4.metric("우리 3Q 투어+앨범 (Base)", f"{tour3 + (alb3 or 0):.1f}십억",
                              f"투어 {tour3:.1f} · 앨범 {(alb3 or 0):.1f} vs 증권사 콘서트 평균 {q['콘서트'].mean():.1f}",
                              delta_color="off")
                qv = q[["broker", "date", "rev", "op", "콘서트", "MD", "로열티", "음반", "tp"]].copy()
                qv.columns = ["증권사", "날짜", "3Q 매출", "3Q 영업이익", "콘서트", "MD", "로열티", "음반", "목표주가"]
                st.dataframe(qv.sort_values("날짜", ascending=False), hide_index=True, use_container_width=True,
                             column_config={"목표주가": st.column_config.NumberColumn(format="%,d")})
                st.caption("3Q26E 부문값은 리포트 분기 추정표에서 추출(십억원). 3Q25 실적: 매출 173.1 · 콘서트 50.8 · MD 28.1 · 로열티 16.3 · 음반 11.8.")

            con = pd.to_numeric(s26["콘서트"], errors="coerce").dropna()
            roy = pd.to_numeric(s26["로열티"], errors="coerce").dropna()
            md = pd.to_numeric(s26["MD"], errors="coerce").dropna()
            rev = pd.to_numeric(s26["rev"], errors="coerce").dropna()
            st.markdown(f"""
**우리 뷰가 컨센을 이기는 길 (variant view)**

1. **콘서트가 핵심 차이.** 우리 2026E 콘서트 {m26.get('콘서트', 0):.1f}십억 vs 증권사 평균 {con.mean():.1f} ({(m26.get('콘서트', 0) / con.mean() - 1) * 100:+.0f}%). 유안타(178.9)만 우리와 같고 나머지는 105~128. 근거: 빅뱅 투어 완료 7개 스탑 전부 매진, 추가 회차(타이베이 3회·싱가포르 2회·오클랜드 2회·방콕 2회) — 증권사 대부분이 추가 회차를 숫자에 덜 넣음. 3Q26E 콘서트도 증권사 평균 {q['콘서트'].mean():.1f}십억(28~62)으로 보수적.
2. **MD는 더 이상 차이가 아님.** 우리 {m26.get('MD라이선싱', 0):.1f} vs 컨센 {md.mean():.1f} — 2Q26 MD 서프라이즈 뒤 증권사가 MD를 올려서 이제 비슷함. 3Q26E MD 27~39십억(3Q25 28.1)으로 디커플링을 증권사도 가정.
3. **로열티는 우리가 낮음.** 우리 {m26.get('로열티', 0):.1f} vs 컨센 {roy.mean():.1f} ({(m26.get('로열티', 0) / roy.mean() - 1) * 100:+.0f}%). 증권사는 빅뱅·베몬 일본 돔 공연을 로열티로 잡음(다올 82.7·NH 64.0). 이 부분은 우리 모델 상향 여지 = 컨센 대비 추가 업사이드.
4. **합계로 보면** 우리 {m26.get('매출', 0):.1f} vs 컨센 평균 {rev.mean():.1f} ({(m26.get('매출', 0) / rev.mean() - 1) * 100:+.0f}%). FnGuide 공식 컨센은 1개월 새 633.9 → 624.0으로 내려와 눈높이가 낮아진 상태. 콘서트(+{m26.get('콘서트', 0) - con.mean():.0f})가 로열티(−{roy.mean() - m26.get('로열티', 0):.0f})를 덮고도 남는 구조.
5. **3Q26 실적(11월 초)이 첫 체크포인트.** 증권사는 YoY 감익(영업이익 11~22십억, 3Q25 31.1)을 깔아 둔 낮은 눈높이. 우리 3Q 투어 바텀업 {tour3 if tour3 is not None else 0:.1f}십억 vs 증권사 3Q 콘서트 평균 {q['콘서트'].mean():.1f}(28~62) — 빅뱅 3Q 회차(고양 3회·오클랜드 2회·메트라이프·파리·런던)가 잡히면 콘서트에서 상단(유안타 62)을 확인할 수 있음.
""")
