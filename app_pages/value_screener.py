# -*- coding: utf-8 -*-
"""밸류 스크리너 — 싸고 좋은 주식 찾기 (Cheap & High-Quality).

Data comes from data/screener/screener_data.csv, extracted from the
Capital IQ comparables workbook (Data sheet, CW:DJ block).

Two tools, same idea as the Excel file:
  1) 티커 조회  — pick one company, see it against its peer group
  2) 조건 검색  — filter the whole market by sector + thresholds
X axis = quality (ROIC+SG or ROE+SG), Y axis = price (a multiple).
Bottom-right = high quality but cheap = worth a deeper look.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from streamlit_searchbox import st_searchbox

sys.path.append(str(Path(__file__).resolve().parent))
from history_fetch import dart_key, load_history  # noqa: E402  (과거 멀티플)

DATA = Path(__file__).resolve().parent.parent / "data" / "screener"

st.set_page_config(page_title="밸류 스크리너", page_icon="📊", layout="wide")

# ---- 입력 위젯 스타일: 엑셀의 노란 입력칸처럼, '바꿀 수 있는 곳'이 한눈에 보이게 ----
st.markdown("""<style>
/* 셀렉트박스 본체 (드롭다운 목록은 어두운 테마 유지) */
div[data-baseweb="select"] > div,
div[data-testid="stSelectbox"] .react-aria-ComboBox > div,
div[data-testid="stSelectbox"] [role="group"] {
    background-color: #fff3c4 !important;
    border: 1px solid #d9b23a !important;
}
div[data-baseweb="select"] > div *,
div[data-testid="stSelectbox"] .react-aria-ComboBox input,
div[data-testid="stSelectbox"] [role="combobox"] {
    color: #222 !important;
    background: transparent !important;
}
div[data-baseweb="select"] svg,
div[data-testid="stSelectbox"] svg { fill: #555 !important; color: #555 !important; }
/* 숫자·텍스트 입력칸 */
div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input {
    background-color: #fff3c4 !important;
    color: #222 !important;
}
div[data-testid="stNumberInput"] button {
    background-color: #efdc9a !important;
}
div[data-testid="stNumberInput"] button svg { fill: #444 !important; }
/* 섹션 제목 아래 구분선 — 그룹끼리 나뉘어 보이게 */
[data-testid="stMarkdownContainer"] h5 {
    border-bottom: 2px solid rgba(217, 178, 58, 0.45);
    padding-bottom: 6px;
    margin-top: 0.7rem;
}
</style>""", unsafe_allow_html=True)

# ---- 차트 점 클릭(네이버금융 링크)이 반드시 '새 탭'으로 열리게 하는 패치 ----
# 차트 렌더러(vega)는 링크 클릭 시 화면에 붙어있지 않은 임시 <a>를 만들어
# 클릭 이벤트를 쏘는데, target이 없어 현재 탭을 덮어써 화면 설정이 초기화된다.
# 그 패턴(떠 있는 앵커)에만 target=_blank를 강제한다.
import streamlit.components.v1 as _components  # noqa: E402

_components.html("""<script>
try {
  const P = window.parent;
  if (!P.__vegaBlankPatch) {
    P.__vegaBlankPatch = true;
    const orig = P.HTMLAnchorElement.prototype.dispatchEvent;
    P.HTMLAnchorElement.prototype.dispatchEvent = function (e) {
      if (!this.isConnected && this.href && !this.getAttribute('target')) {
        this.setAttribute('target', '_blank');
        this.setAttribute('rel', 'noopener');
      }
      return orig.call(this, e);
    };
  }
} catch (err) {}
</script>""", height=0)

# ---------------------------------------------------------------- constants
MULTIPLES = {  # label -> column
    "EV/Sales": "ev_sales",
    "EV/EBIT": "ev_ebit",
    "EV/EBITDA": "ev_ebitda",
    "EV/FCF": "ev_fcf",     # LTM 전용 (FCF는 forward 컨센서스가 거의 없음)
    "PER": "per",
    "PBR": "pbr",
}
X_AXES = {"ROIC+SG": "roic_sg", "ROE+SG": "roe_sg"}
CLASS_LEVELS = {  # label -> column
    "Industry Sector": "sector",
    "Industry Group": "industry_group",
    "Industry": "industry",
    "Primary Industry": "primary_industry",
    "Primary SIC Industry": "sic_industry",
}
# 멀티플별 기본 상한 (엑셀 F열 기본값과 동일; EV/FCF는 FCF 변동성 감안해 넉넉히)
DEFAULT_Y_MAX = {"EV/Sales": 2.0, "EV/EBIT": 15.0, "EV/EBITDA": 20.0, "EV/FCF": 20.0,
                 "PER": 20.0, "PBR": 2.0}

C_PEER = "#9ab6d8"     # 회색-파랑: 나머지 종목
C_MATCH = "#2a78d6"    # 파랑: 조건 통과 종목 (2026E 추정치 기준)
C_PICK = "#eb6834"     # 주황: 선택한 종목
C_LTM = "#d9a021"      # 노랑: 2026E 추정치가 없어서 LTM으로 대체된 종목


@st.cache_data(ttl=3600, show_spinner=False)
def load():
    df = pd.read_csv(DATA / "screener_data.csv")
    # 원본 워크북에 중복 티커가 있어 표에 같은 종목이 두 번 나오는 것 방지
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    # 데이터 파일이 코드보다 오래된 경우에도 죽지 않게, 없는 멀티플 컬럼은 빈 값으로
    for _c in MULTIPLES.values():
        if _c not in df.columns:
            df[_c] = np.nan
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    df["label"] = df["company"] + " (" + df["ticker"] + ")"
    # 차트에서 점 클릭 → 네이버금융 종목 페이지
    df["naver"] = ("https://finance.naver.com/item/main.naver?code="
                   + df["ticker"].str.lstrip("A"))
    return df, meta


def r_square(x: pd.Series, y: pd.Series) -> float:
    """두 값의 상관관계 R² (0~1). 데이터가 부족하면 nan."""
    m = x.notna() & y.notna()
    if m.sum() < 3 or x[m].std() == 0 or y[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(x[m], y[m])[0, 1] ** 2)


def signed_r(x: pd.Series, y: pd.Series) -> float:
    """부호 있는 상관계수 R (-1~1). 양수 = 우상향 관계. 데이터 부족이면 nan."""
    m = x.notna() & y.notna()
    if m.sum() < 3 or x[m].std() == 0 or y[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(x[m], y[m])[0, 1])


def drop_iqr(d: pd.DataFrame, xc: str, yc: str) -> pd.DataFrame:
    """IQR 기준 극단값 행 제거 (양 축)."""
    if len(d) < 5:
        return d
    q1y, q3y = d[yc].quantile([0.25, 0.75])
    iy = q3y - q1y
    q1x, q3x = d[xc].quantile([0.25, 0.75])
    ix = q3x - q1x
    return d[~((d[yc] > q3y + 1.5 * iy) | (d[yc] < q1y - 1.5 * iy)
               | (d[xc] > q3x + 1.5 * ix) | (d[xc] < q1x - 1.5 * ix))]


def best_relationship(df: pd.DataFrame, drop_outliers: bool = False) -> tuple[str, str, float]:
    """'질이 좋을수록 멀티플이 높다'는 방향(양의 상관)이 맞는 조합 중
    상관계수 R가 가장 높은 X·멀티플 조합을 찾는다.
    R²는 방향을 무시해서 우하향(거꾸로) 관계도 높게 나오므로 부호 있는 R를 쓴다."""
    best = ("", "", -1.0)
    for xl, xc in X_AXES.items():
        for yl, yc in MULTIPLES.items():
            if xc not in df.columns or yc not in df.columns:
                continue
            d = df[df[xc].notna() & df[yc].notna() & (df[yc] > 0)]
            if drop_outliers:
                d = drop_iqr(d, xc, yc)
            r = signed_r(d[xc], d[yc])
            if not np.isnan(r) and r > best[2]:
                best = (xl, yl, r)
    return best


def scatter(df: pd.DataFrame, x_col: str, y_col: str, x_label: str, y_label: str,
            x_min: float, y_max: float, pick: pd.DataFrame | None = None,
            label_matches: bool = False, rules: bool = True,
            drop_outliers: bool = False) -> alt.Chart:
    """산점도: 조건 통과는 파랑, 나머지는 연한 색, 선택 종목은 주황 별."""
    d = df[df[x_col].notna() & df[y_col].notna() & (df[y_col] > 0)].copy()
    # 극단값은 차트를 망가뜨리므로 표시 범위만 잘라낸다 (데이터는 그대로)
    if len(d) > 20:
        x_lo, x_hi = d[x_col].quantile([0.01, 0.99])
        y_hi = d[y_col].quantile(0.99)
        d = d[(d[x_col] >= x_lo) & (d[x_col] <= x_hi) & (d[y_col] <= max(y_hi, y_max))]
    # 축 범위를 '조건 값'에 앵커해서 고정한다 — 같은 조건에서는 화면 틀이
    # 절대 안 움직이고 점만 나타났다 사라진다 (드래그/줌은 그대로 가능).
    # X 왼쪽 = 조건값(또는 데이터 최소), Y 위쪽 = 조건값(또는 데이터 최대) 약간 위.
    if len(d):
        # 오른쪽 끝은 최댓값 대신 97.5% 지점까지만 — 극단값 하나가 화면을
        # 옆으로 길게 늘리는 것 방지 (그 밖의 점은 표시에서 제외)
        x_right = float(d[x_col].quantile(0.975))
        x_left = max(x_min, float(d[x_col].min()))
        span_x = (x_right - x_left) or 0.01
        x_dom = [x_left - span_x * 0.03, x_right + span_x * 0.03]
        y_top = min(y_max, float(d[y_col].max()))
        y_dom = [0.0, y_top * 1.07]
        # 선택한 종목(주황 다이아몬드)이 조건 밖이어도 화면에는 항상 보이게
        if pick is not None and len(pick):
            pv = pick.iloc[0]
            if pd.notna(pv[x_col]):
                x_dom[0] = min(x_dom[0], float(pv[x_col]) - span_x * 0.03)
                x_dom[1] = max(x_dom[1], float(pv[x_col]) + span_x * 0.03)
            if pd.notna(pv[y_col]) and pv[y_col] > 0:
                y_dom[1] = max(y_dom[1], float(pv[y_col]) * 1.07)
    else:
        x_dom = y_dom = None

    # 조건을 통과한 종목만 차트에 그린다 (고정 화면 밖 극단값도 제외)
    d["통과"] = (d[x_col] > x_min) & (d[y_col] < y_max)
    d = d[d["통과"]]
    if x_dom is not None:
        d = d[(d[x_col] >= x_dom[0]) & (d[x_col] <= x_dom[1])]
    if drop_outliers and len(d) >= 5:
        # IQR 기준 극단값 종목을 차트·추세선에서 제외 (아래 통과 목록에는 그대로 있음)
        q1y, q3y = d[y_col].quantile([0.25, 0.75])
        iy = q3y - q1y
        q1x, q3x = d[x_col].quantile([0.25, 0.75])
        ix = q3x - q1x
        d = d[~((d[y_col] > q3y + 1.5 * iy) | (d[y_col] < q1y - 1.5 * iy)
                | (d[x_col] > q3x + 1.5 * ix) | (d[x_col] < q1x - 1.5 * ix))]

    # 추세선(회귀선): 선 아래에 있으면 같은 질 대비 멀티플이 낮다 = 싸 보인다
    trend = None
    if len(d) >= 3 and d[x_col].std() > 0:
        slope, intercept = np.polyfit(d[x_col], d[y_col], 1)
        d["추세대비"] = d[y_col] - (slope * d[x_col] + intercept)
        x1, x2 = float(d[x_col].min()), float(d[x_col].max())
        y1, y2 = slope * x1 + intercept, slope * x2 + intercept
        # 선이 0 아래로 내려가면 y=0 지점에서 잘라낸다 (축이 음수로 늘어나지 않게)
        if min(y1, y2) < 0 and slope != 0:
            x_zero = -intercept / slope
            if y1 < 0:
                x1, y1 = x_zero, 0.0
            if y2 < 0:
                x2, y2 = x_zero, 0.0
        if max(y1, y2) > 0:
            xs = pd.DataFrame({x_col: [x1, x2], y_col: [y1, y2]})
            trend = alt.Chart(xs).mark_line(
                color="#d43a2f", strokeDash=[5, 4], size=2, opacity=0.9, clip=True,
            ).encode(x=x_col, y=y_col)
    else:
        d["추세대비"] = np.nan

    # 멀티플 기준 표시: 2026E 추정치를 썼는지, 없어서 LTM으로 대체됐는지
    src = f"{y_col}_src"
    if src in d.columns and d[src].eq("LTM").any():
        d["기준"] = d[src].map({"2026E": "2026E 추정", "LTM": "LTM 대체"}).fillna("LTM 대체")
        color_enc = alt.Color(
            "기준:N",
            scale=alt.Scale(domain=["2026E 추정", "LTM 대체"], range=[C_MATCH, C_LTM]),
            legend=alt.Legend(title="멀티플 기준", orient="top-right"))
    else:
        d["기준"] = "2026E 추정" if src in d.columns else "현재값"
        color_enc = alt.value(C_MATCH)

    x_scale = alt.Scale(domain=x_dom, nice=False) if x_dom else alt.Undefined
    y_scale = alt.Scale(domain=y_dom, nice=False) if y_dom else alt.Undefined
    base = alt.Chart(d).mark_circle(size=55, opacity=0.75, cursor="pointer").encode(
        x=alt.X(x_col, title=f"{x_label} (높을수록 좋은 회사)", axis=alt.Axis(format="%"),
                scale=x_scale),
        y=alt.Y(y_col, title=f"{y_label} (낮을수록 싼 주식)", scale=y_scale),
        color=color_enc,
        href=alt.Href("naver:N") if "naver" in d.columns else alt.Undefined,
        tooltip=[alt.Tooltip("company", title="회사"),
                 alt.Tooltip("ticker", title="티커"),
                 alt.Tooltip(x_col, title=x_label, format=".1%"),
                 alt.Tooltip(y_col, title=y_label, format=".2f"),
                 alt.Tooltip("기준", title="멀티플 기준"),
                 alt.Tooltip("추세대비", title="추세선 대비 (음수=선 아래)", format="+.2f"),
                 alt.Tooltip("sector", title="섹터")],
    )
    layers = [base]
    if rules:
        # 기준선 — 섹터 드릴다운처럼 조건이 없는 차트에서는 끈다 (축이 기준선
        # 위치까지 늘어나 점이 뭉개지는 것 방지)
        layers.append(alt.Chart(pd.DataFrame({"v": [x_min]})).mark_rule(
            strokeDash=[5, 4], color="#888", clip=True).encode(x=alt.X("v", scale=x_scale)))
        layers.append(alt.Chart(pd.DataFrame({"v": [y_max]})).mark_rule(
            strokeDash=[5, 4], color="#888", clip=True).encode(y=alt.Y("v", scale=y_scale)))
    if trend is not None:
        layers.append(trend)

    if label_matches:
        # 다크/라이트 테마에 따라 읽기 좋은 글자색을 고른다
        try:
            dark = st.context.theme.type == "dark"
        except Exception:
            dark = False
        hits = d[d["통과"]]
        if pick is not None and not pick.empty:
            # 선택한 종목은 주황색 라벨이 따로 붙으므로 파란 라벨은 생략
            hits = hits[hits["ticker"] != pick.iloc[0]["ticker"]]
        layers.append(alt.Chart(hits).mark_text(
            dy=-10, fontSize=12, fontWeight="bold",
            color="#9ecbff" if dark else "#1a5cad",
        ).encode(x=x_col, y=y_col, text="company"))

    if pick is not None and not pick.empty:
        p = pick[pick[x_col].notna() & pick[y_col].notna()]
        if not p.empty:
            layers.append(alt.Chart(p).mark_point(
                shape="diamond", size=320, filled=True, color=C_PICK,
                stroke="white", strokeWidth=1.5,
            ).encode(x=x_col, y=y_col,
                     tooltip=[alt.Tooltip("company", title="회사"),
                              alt.Tooltip(x_col, title=x_label, format=".1%"),
                              alt.Tooltip(y_col, title=y_label, format=".2f")]))
            layers.append(alt.Chart(p).mark_text(
                dy=-16, fontSize=13, fontWeight="bold", color=C_PICK,
            ).encode(x=x_col, y=y_col, text="company"))

    chart = alt.layer(*layers).properties(height=700).interactive()
    # 점 클릭(네이버금융 링크)이 현재 페이지를 덮지 않고 새 탭으로 열리게
    chart.usermeta = {"embedOptions": {"loader": {"target": "_blank"}}}
    return chart


def match_table(d: pd.DataFrame, x_col: str, y_col: str, x_label: str, y_label: str,
                key: str = "dl", score: bool = False):
    """조건 통과 종목 표 + CSV 다운로드. score=True면 '좋은데 싼' 점수순 정렬."""
    src = f"{y_col}_src"
    cols = ["company", "ticker", "sector", x_col, y_col, "mcap"] + ([src] if src in d.columns else [])
    t = d[cols].copy()
    if score:
        # 점수 = 질 백분위 + (100 - 멀티플 백분위) 평균 → 높을수록 '좋은데 싼' 종목
        t["_score"] = ((t[x_col].rank(pct=True)
                        + (1 - t[y_col].rank(pct=True))) / 2 * 100).round(0)
        t = t.sort_values("_score", ascending=False)
    else:
        t = t.sort_values(y_col)
    t[x_col] = (t[x_col] * 100).round(1)
    t[y_col] = t[y_col].round(2)
    t["mcap"] = (t["mcap"] / 1000).round(0).astype("Int64")  # KRW mm -> KRW bn
    if src in t.columns:
        t[src] = t[src].map({"2026E": "2026E 추정", "LTM": "LTM 대체"}).fillna("")
    # 네이버금융 + 종목 상세 페이지 링크
    t["naver"] = ("https://finance.naver.com/item/main.naver?code="
                  + t["ticker"].str.lstrip("A"))
    t["detail"] = "/종목상세?ticker=" + t["ticker"]
    if score:
        t = t[["company", "ticker", "sector", "_score", x_col, y_col, "mcap"]
              + ([src] if src in cols else []) + ["detail", "naver"]]
        t.columns = (["회사", "티커", "섹터", "점수", f"{x_label} (%)", y_label, "시총(십억원)"]
                     + (["멀티플 기준"] if src in cols else []) + ["상세", "네이버금융"])
    else:
        t = t[["company", "ticker", "sector", x_col, y_col, "mcap"]
              + ([src] if src in cols else []) + ["detail", "naver"]]
        t.columns = (["회사", "티커", "섹터", f"{x_label} (%)", y_label, "시총(십억원)"]
                     + (["멀티플 기준"] if src in cols else []) + ["상세", "네이버금융"])
    st.dataframe(t, use_container_width=True, hide_index=True, height=320,
                 column_config={
                     "네이버금융": st.column_config.LinkColumn(
                         "네이버금융", display_text="📈 종목 페이지"),
                     "상세": st.column_config.LinkColumn(
                         "상세", display_text="📋 상세")})
    st.download_button("⬇️ CSV로 받기", t.to_csv(index=False).encode("utf-8-sig"),
                       "screener_matches.csv", "text/csv", key=key)


df, meta = load()

st.title("📊 밸류 스크리너")
_fwd_note = ""
if meta.get("basis"):
    _fwd_note = (f" · 멀티플은 **2026년 추정치(컨센서스)** 기준"
                 f" ({meta.get('n_fwd', 0):,}개사), 추정치가 없는 종목은 LTM으로 대체")
st.caption(f"한국 상장사 {meta['n_companies']:,}개 · 기준일 {meta['as_of']}{_fwd_note} · "
           "X축 = 회사의 질(수익성+성장), Y축 = 주가의 비싼 정도(멀티플). "
           "**오른쪽 아래**에 있을수록 '좋은데 싼' 주식입니다.")

tab1, tab2, tab3 = st.tabs(["🔍 티커 조회", "🧮 조건 검색", "🏭 섹터별 보기"])

# ================================================= 1) Ticker Input
with tab1:
    c1, c2 = st.columns([1, 3.2], gap="large")
    with c1:
        # 종목 검색 — 입력한 단어가 '포함된' 종목만 (기본 셀렉트박스는 퍼지 매칭이라
        # cosmax를 쳐도 엉뚱한 SPAC이 섞여 나온다)
        _stock_labels = df["label"].sort_values().tolist()

        def _search_stocks(q: str):
            ql = q.strip().lower()
            if not ql:
                return []
            return [s for s in _stock_labels if ql in s.lower()][:60]

        pick_label = st_searchbox(_search_stocks, key="ti_pick_sb",
                                  label="종목 (이름이나 티커로 검색)",
                                  placeholder="예: SILICON2 또는 A257720",
                                  clear_on_submit=False)
        ALL_LVL = "(전체)"
        class_label = st.selectbox("피어그룹 기준 (분류 단계)", [ALL_LVL] + list(CLASS_LEVELS),
                                   index=1,
                                   help="선택한 회사와 같은 분류에 속한 회사들을 비교 대상으로 잡습니다. "
                                        "아래로 갈수록 더 좁고 비슷한 그룹입니다. "
                                        "(전체)를 고르면 아래 수동 설정에서 5개 분류 단계를 "
                                        "한꺼번에 검색할 수 있습니다.")
        # 피어그룹 수동 설정 — 여러 사업을 하는 회사(예: 동국제약 = 제약+화장품)를
        # 원하는 다른 산업의 피어들과 비교하고 싶을 때 직접 고른다
        AUTO_PEER = "(자동 — 선택한 종목과 같은 분류)"
        if class_label == ALL_LVL:
            # (전체): 박스에 바로 타이핑하면 5개 분류 전체에서 '단어가 포함된'
            # 그룹만 나온다 (기본 셀렉트박스의 퍼지 검색 대신 엄격한 포함 검색).
            opts_all = [f"{v}  [{lvl}]"
                        for lvl, col in CLASS_LEVELS.items()
                        for v in sorted(df[col].dropna().unique())]

            def _search_groups(q: str):
                ql = q.strip().lower()
                return [o for o in opts_all if ql in o.lower()][:60]

            st.markdown("피어그룹 수동 설정")
            manual_peer = st_searchbox(
                _search_groups, key="ti_manual_sb",
                placeholder="타이핑해서 검색 — 예: cosmetics, personal, health …",
                clear_on_submit=False) or AUTO_PEER
            st.caption("비워두면 자동(선택한 종목의 Industry Sector)입니다.")
        else:
            _mcol = CLASS_LEVELS[class_label]
            manual_opts = [AUTO_PEER] + sorted(df[_mcol].dropna().unique())
            manual_peer = st.selectbox(
                "피어그룹 수동 설정", manual_opts, index=0, key=f"ti_manual_{_mcol}",
                help="기본은 자동(선택한 종목의 분류). 화장품 사업도 하는 제약사를 "
                     "화장품 피어들과 비교하고 싶을 때처럼 다른 그룹을 직접 지정할 수 "
                     "있습니다. 분류 단계를 (전체)로 두면 5개 단계 전체에서 검색됩니다.")
        st.markdown("##### 📌 주요변수 선택")
        auto1 = st.toggle("추천 변수 (상관 높은 조합 자동)", value=True, key="ti_auto",
                          help="켜져 있으면 피어그룹에서 우상향(질↑=멀티플↑) 상관이 "
                               "가장 높은 X·Y 조합을 자동으로 씁니다. 끄면 직접 고르는 "
                               "수동 설정이 됩니다.")
        if not auto1:
            y_label1 = st.selectbox("Y축 (멀티플)", list(MULTIPLES), index=0, key="ti_y")
            x_label1 = st.selectbox("X축", list(X_AXES), index=0, key="ti_x")
        out1 = st.toggle("극단값 제외 (추세선 보정)", value=False, key="ti_outlier",
                         help="동떨어진 종목(IQR 기준)을 차트와 추세선에서 뺍니다. "
                              "아래 통과 목록에는 그대로 남습니다.")

        # 종목이 정해졌으면 피어그룹·추천조합을 이 자리에서 바로 계산해 그린다
        # (빈 슬롯을 나중에 채우면 +/- 클릭 때마다 화면이 출렁이므로 한 번에 렌더)
        peers = None
        bx = by = ""
        br = -1.0
        if pick_label is not None:
            pick = df[df["label"] == pick_label]
            row = pick.iloc[0]
            if class_label == ALL_LVL:
                if manual_peer == AUTO_PEER:
                    # (전체) + 자동이면 가장 넓은 단계(Industry Sector) 기준으로
                    class_col = CLASS_LEVELS["Industry Sector"]
                    peer_val = row[class_col]
                else:
                    v, lvl_label = manual_peer.rsplit("  [", 1)
                    class_col = CLASS_LEVELS[lvl_label.rstrip("]")]
                    peer_val = v
            else:
                class_col = CLASS_LEVELS[class_label]
                peer_val = row[class_col] if manual_peer == AUTO_PEER else manual_peer
            peers = df[df[class_col] == peer_val]
            bx, by, br = best_relationship(peers, drop_outliers=out1)
            if auto1:
                if br > 0:
                    x_label1, y_label1 = bx, by
                    st.info(f"🤖 **자동 선택**: X **{bx}** · Y **{by}** "
                            f"(R = {br:.2f}) — 이 피어그룹에서 우상향 상관이 "
                            "가장 높은 조합입니다.")
                else:
                    x_label1, y_label1 = "ROIC+SG", "EV/Sales"
                    st.info("우상향 상관 조합이 없어 기본값 X ROIC+SG · "
                            "Y EV/Sales를 사용합니다.")
        if pick_label is not None or not auto1:
            st.markdown("##### 🎯 주요조건 입력")
            y_max1 = st.number_input(f"{y_label1} 이하", value=DEFAULT_Y_MAX[y_label1],
                                     step=0.5, key=f"ti_ymax_{MULTIPLES[y_label1]}")
            x_min1 = st.number_input(f"{x_label1} 이상 (%)", value=0.0, step=5.0,
                                     key="ti_xmin") / 100

    if pick_label is None:
        with c2:
            st.info("왼쪽에서 종목을 선택하면 피어그룹 차트가 나옵니다.")
    else:
        x_col, y_col = X_AXES[x_label1], MULTIPLES[y_label1]
        good = peers[(peers[x_col] > x_min1) & (peers[y_col] > 0) & (peers[y_col] < y_max1)]

        with c1:
            st.markdown(f"**{row['company']}**")
            _tag = "" if manual_peer == AUTO_PEER else " · 수동 설정"
            st.markdown(f"- 섹터: {row['sector']}\n- 산업: {row['industry']}\n"
                        f"- 피어그룹: {peer_val} ({len(peers)}개사){_tag}")
            rr = signed_r(good[x_col], good[y_col])
            st.markdown(f"- 현재 조합 R = {rr:.2f}" if not np.isnan(rr)
                        else "- 현재 조합 R: 계산 불가")
            if not auto1 and br > 0:
                st.info(f"💡 **추천 조합**: 이 그룹에서는 **X {bx} · Y {by}** 조합이 "
                        f"우상향 관계로 설명력이 가장 높습니다 (R = {br:.2f}). "
                        "직접 바꾸거나 위의 '추천 변수' 토글을 켜면 자동 적용됩니다.")

        with c2:
            st.altair_chart(scatter(peers, x_col, y_col, x_label1, y_label1,
                                    x_min1, y_max1, pick=pick, label_matches=True,
                                    drop_outliers=out1),
                            use_container_width=True)
            mine = pick.iloc[0]
            vx = f"{mine[x_col]:.1%}" if pd.notna(mine[x_col]) else "없음"
            vy = f"{mine[y_col]:.2f}" if pd.notna(mine[y_col]) else "없음"
            st.caption(f"🔶 {row['company']}: {x_label1} {vx} · {y_label1} {vy}")

        # ------------------------- 과거 멀티플 (선택 종목) -------------------------
        st.markdown(f"#### 📈 과거 멀티플 — {row['company']}")
        # 1순위: Capital IQ 월별 히스토리 (관심종목 — history_ciq_update.py로 미리 추출)
        # 2순위: 전 종목 사전 계산 DB (histdb) · 3순위: 네이버+DART 즉석 계산
        ciq_csv = DATA / "history_ciq" / f"{row['ticker']}.csv"
        use_ciq = ciq_csv.exists()
        hdb_row = None
        if not use_ciq:
            _hdb_p = DATA.parent / "histdb" / "multiples.csv.gz"
            if _hdb_p.exists():
                @st.cache_data(ttl=3600, show_spinner=False)
                def _load_hdb():
                    x = pd.read_csv(_hdb_p)
                    x["date"] = pd.to_datetime(x["date"]).dt.date
                    return x
                _hdb = _load_hdb()
                hdb_row = _hdb[_hdb["ticker"] == row["ticker"]]
                if len(hdb_row) < 6:
                    hdb_row = None
        if not use_ciq and hdb_row is None and not dart_key():
            st.info("이 종목은 사전 계산 데이터가 없고, 즉석 계산용 DART 접근도 "
                    "불가한 환경입니다.")
        else:
            if use_ciq:
                HIST_METRIC = {"EV/Sales": ("evs", "EV/Sales (LTM)"),
                               "EV/EBIT": ("eve", "EV/EBIT (LTM)"),
                               "EV/EBITDA": ("ebitda", "EV/EBITDA (LTM)"),
                               "EV/FCF": ("fcf", "EV/FCF (LTM)"),
                               "PER": ("per", "PER (LTM)"),
                               "PBR": ("pbr", "PBR")}
            else:
                # DB/즉석 계산은 감가상각·capex를 알 수 없어 EV/EBIT로 대신 보여준다
                HIST_METRIC = {"EV/Sales": ("evs", "EV/Sales (TTM)"),
                               "EV/EBIT": ("eve", "EV/EBIT (TTM)"),
                               "EV/EBITDA": ("eve", "EV/EBIT (TTM · EV/EBITDA 대용)"),
                               "EV/FCF": ("eve", "EV/EBIT (TTM · EV/FCF 대용)"),
                               "PER": ("per", "PER (TTM)"),
                               "PBR": ("pbr", "PBR")}
            hcol, hname = HIST_METRIC[y_label1]
            c3, c4 = st.columns([1, 3.2], gap="large")
            with c3:
                dur = st.radio("기간", ["1년", "3년", "5년", "10년(최대)", "직접설정"],
                               index=2, key="hist_dur")
                d_end = dt.date.today()
                if dur == "직접설정":
                    d_start = st.date_input("시작일", value=d_end - dt.timedelta(days=365 * 3),
                                            key="hist_d1")
                    d_end = st.date_input("종료일", value=d_end, key="hist_d2")
                else:
                    days = {"1년": 365, "3년": 365 * 3, "5년": 365 * 5, "10년(최대)": 3650}[dur]
                    d_start = d_end - dt.timedelta(days=days)
            hist = None
            if use_ciq:
                hist = pd.read_csv(ciq_csv)
                hist["date"] = pd.to_datetime(hist["date"]).dt.date
                hmeta = None
                if hcol not in hist.columns:
                    # 예전에 추출한 CSV라 이 지표가 없으면 EV/EBIT로 대체
                    hcol, hname = "eve", f"EV/EBIT (LTM · {y_label1} 대용)"
            elif hdb_row is not None:
                hist = hdb_row     # 전 종목 사전 계산 DB — 즉시 로딩
                hmeta = None
            else:
                try:
                    with st.spinner("네이버·DART에서 과거 데이터를 불러오는 중… "
                                    "(종목당 첫 조회만 10초쯤 걸립니다)"):
                        hist, hmeta = load_history(row["ticker"].lstrip("A"))
                except Exception as e:
                    # 예외 원문에 API 키가 섞일 수 있어 표시하지 않는다
                    if "opendart" in str(e) or "timed out" in str(e).lower():
                        st.info("서버에서 DART에 접속할 수 없어 즉석 계산이 불가합니다 "
                                "(해외 서버 차단). 사전 계산된 종목만 표시됩니다.")
                    else:
                        st.warning(f"과거 데이터 조회 실패 ({type(e).__name__})")
            if hist is not None and not hist.empty:
                h = hist[hist[hcol].notna()
                         & (hist["date"] >= d_start) & (hist["date"] <= d_end)]
                if h.empty:
                    with c4:
                        st.info("이 구간에는 표시할 데이터가 없습니다 (적자 구간 등).")
                else:
                    avg = float(h[hcol].mean())
                    last = float(h[hcol].iloc[-1])
                    fwd = float(row[y_col]) if pd.notna(row[y_col]) else None
                    tips = [alt.Tooltip("date:T", title="날짜"),
                            alt.Tooltip(hcol, title=hname, format=".2f")]
                    if "px" in h.columns:
                        tips.append(alt.Tooltip("px", title="주가", format=",.0f"))
                    if "q" in h.columns:
                        tips.append(alt.Tooltip("q", title="TTM 기준분기"))
                    line = alt.Chart(h).mark_line(color=C_MATCH, size=2).encode(
                        x=alt.X("date:T", title=None),
                        y=alt.Y(hcol, title=hname,
                                scale=alt.Scale(zero=False)),
                        tooltip=tips)
                    mean_rule = alt.Chart(pd.DataFrame({"v": [avg]})).mark_rule(
                        strokeDash=[6, 4], color="#888", size=1.5).encode(y="v")
                    layers = [line, mean_rule]
                    if fwd is not None:
                        layers.append(alt.Chart(pd.DataFrame({"v": [fwd]})).mark_rule(
                            strokeDash=[2, 3], color=C_PICK, size=2).encode(y="v"))
                    with c4:
                        st.altair_chart(alt.layer(*layers).properties(height=380)
                                        .interactive(), use_container_width=True)
                    with c3:
                        st.markdown(f"**{hname}**\n- 현재(TTM): **{last:.2f}배**\n"
                                    f"- 기간 평균: **{avg:.2f}배**"
                                    + (f"\n- 2026E 기준: **{fwd:.2f}배** (주황 점선)"
                                       if fwd is not None else ""))
                        if use_ciq:
                            st.caption("회색 점선 = 기간 평균. 파란 선 = 월별 LTM 멀티플. "
                                       "**데이터: Capital IQ** (관심종목 — "
                                       "`history_ciq_update.py`로 갱신, 목록에 종목 추가 가능).")
                        elif hmeta is None:
                            st.caption("회색 점선 = 기간 평균. 파란 선 = 월별 TTM 멀티플. "
                                       "**데이터: 사전 계산 DB** (`histdb_update.py`로 갱신) · "
                                       "순부채·주식수는 최신값 고정 근사라 CapIQ 수치와 다소 다를 수 있습니다.")
                        else:
                            st.caption("회색 점선 = 기간 평균. 파란 선 = 주간 TTM 멀티플. "
                                       f"재무 {hmeta['quarters']} · "
                                       "가격 네이버 주간종가 · 재무 DART 연결 TTM(공시지연 45일 가정) · "
                                       "순부채·주식수는 최신값 고정 근사라 CapIQ 수치와 다소 다를 수 있습니다.")

        st.markdown(f"#### 조건 통과 (좋은데 싼) 피어: {len(good)}개")
        st.caption("점수(질 백분위 + 멀티플 낮음 백분위, 100점 만점) 높은 순 · "
                   "차트의 점을 클릭하면 네이버금융 종목 페이지가 열립니다.")
        match_table(good, x_col, y_col, x_label1, y_label1, key="dl_ticker", score=True)

# ================================================= 2) Screen Panel
with tab2:
    c1, c2 = st.columns([1, 3.2], gap="large")
    with c1:
        st.markdown("##### 🏭 산업분류 선택")
        # 통합 산업 검색 — 타이핑하면 5개 분류 단계 전체에서 찾아준다.
        # 예: 'health' → Health Care [Industry Sector], Health Care Equipment
        # and Services [Industry Group] … 중에서 골라 바로 필터링.
        all_opts = [f"{v}  [{lvl_label}]"
                    for lvl_label, lvl_col in CLASS_LEVELS.items()
                    for v in sorted(df[lvl_col].dropna().unique())]

        def _search_inds(q: str):
            ql = q.strip().lower()
            if not ql:
                return []
            return [o for o in all_opts if ql in o.lower()][:60]

        sel_search = st_searchbox(_search_inds, key="sp_isearch_sb",
                                  label="🔎 산업 검색 (모든 분류 단계에서 찾기)",
                                  placeholder="예: health, semiconductor, personal …",
                                  clear_on_submit=False,
                                  help="입력한 단어가 이름에 포함된 그룹만 5개 분류 전체에서 "
                                       "찾아줍니다. 하나 고르면 그 분류로 바로 필터링돼요.")
        filt = df
        if sel_search:
            v, lvl_label = sel_search.rsplit("  [", 1)
            filt = filt[filt[CLASS_LEVELS[lvl_label.rstrip("]")]] == v]
        # 분류 필터 — 위에서 고르면 아래 선택지가 그 안으로 좁혀진다
        for lvl_label, lvl_col in CLASS_LEVELS.items():
            opts = ["(전체)"] + sorted(filt[lvl_col].dropna().unique())
            sel = st.selectbox(lvl_label, opts, key=f"sp_{lvl_col}")
            if sel != "(전체)":
                filt = filt[filt[lvl_col] == sel]

        st.markdown("##### 📌 주요변수 선택")
        auto2 = st.toggle("추천 변수 (상관 높은 조합 자동)", value=True, key="sp_auto",
                          help="켜져 있으면 위 산업분류 필터 안에서 우상향 상관이 "
                               "가장 높은 X·Y 조합을 자동으로 씁니다. 끄면 직접 고르는 "
                               "수동 설정이 됩니다.")
        if not auto2:
            y_label2 = st.selectbox("Y축 (멀티플)", list(MULTIPLES), index=1, key="sp_y")
            x_label2 = st.selectbox("X축", list(X_AXES), index=0, key="sp_x")
        out2 = st.toggle("극단값 제외 (추세선 보정)", value=False, key="sp_outlier",
                         help="동떨어진 종목(IQR 기준)을 차트와 추세선에서 뺍니다. "
                              "아래 통과 목록에는 그대로 남습니다.")
        bx2, by2, br2_ = best_relationship(filt, drop_outliers=out2)
        if auto2:
            if br2_ > 0:
                x_label2, y_label2 = bx2, by2
                st.info(f"🤖 **자동 선택**: X **{bx2}** · Y **{by2}** "
                        f"(R = {br2_:.2f}) — 현재 산업분류 필터 안에서 우상향 "
                        "상관이 가장 높은 조합입니다.")
            else:
                x_label2, y_label2 = "ROIC+SG", "EV/EBIT"
                st.info("우상향 상관 조합이 없어 기본값 X ROIC+SG · Y EV/EBIT를 "
                        "사용합니다.")
        st.markdown("##### 🎯 주요조건 입력")
        y_max2 = st.number_input(f"{y_label2} 이하", value=DEFAULT_Y_MAX[y_label2],
                                 step=0.5, key=f"sp_ymax_{MULTIPLES[y_label2]}")
        x_min2 = st.number_input(f"{x_label2} 이상 (%)", value=20.0, step=5.0,
                                 key="sp_xmin") / 100

    x_col, y_col = X_AXES[x_label2], MULTIPLES[y_label2]
    good = filt[(filt[x_col] > x_min2) & (filt[y_col] > 0) & (filt[y_col] < y_max2)]

    with c1:
        rr2 = signed_r(good[x_col], good[y_col])
        st.markdown(f"**대상 {len(filt):,}개사 · 조건 통과 {len(good)}개**")
        if not np.isnan(rr2):
            st.caption(f"R = {rr2:.2f} — X와 멀티플의 상관 정도 (양수=우상향)")
        if not auto2 and br2_ > 0:
            st.info(f"💡 **추천 조합**: 이 조건에서는 **X {bx2} · Y {by2}** 조합이 "
                    f"우상향 관계로 설명력이 가장 높습니다 (R = {br2_:.2f}). "
                    "직접 바꾸거나 위의 '추천 변수' 토글을 켜면 자동 적용됩니다.")

    with c2:
        st.altair_chart(scatter(filt, x_col, y_col, x_label2, y_label2, x_min2, y_max2,
                                label_matches=True, drop_outliers=out2),
                        use_container_width=True)

    st.markdown(f"#### 조건 통과 종목: {len(good)}개")
    st.caption("점수(질 백분위 + 멀티플 낮음 백분위, 100점 만점) 높은 순 · "
               "차트의 점을 클릭하면 네이버금융 종목 페이지가 열립니다.")
    match_table(good, x_col, y_col, x_label2, y_label2, key="dl_screen", score=True)

# ================================================= 3) Sector View
with tab3:
    c1, c2 = st.columns([1, 3.2], gap="large")
    with c1:
        st.markdown("##### 🏭 산업분류 선택")
        lvl_label3 = st.selectbox("분류 단계", list(CLASS_LEVELS), index=0, key="sv_lvl",
                                  help="점 하나 = 이 분류 단계의 그룹 하나. "
                                       "아래로 갈수록 더 잘게 쪼개집니다.")
        lvl_col3 = CLASS_LEVELS[lvl_label3]
        min_n = int(st.number_input("그룹 최소 종목 수", value=5, min_value=1, step=1,
                                    key="sv_minn",
                                    help="종목이 이보다 적은 그룹은 평균이 불안정해서 뺍니다."))
        fix_out = st.toggle("극단값 제외 (추세선 보정)", value=False, key="sv_outlier",
                            help="평균이 유독 동떨어진 그룹(IQR 기준)을 차트와 추세선에서 "
                                 "빼서, 극단값 한두 개가 추세선을 왜곡하는 것을 막습니다.")

        st.markdown("##### 📌 주요변수 선택")
        # 기본은 '추천 변수' — 우상향 상관이 가장 높은 X·Y 조합을 자동으로 쓴다.
        # 토글을 끄면 수동 설정 (직접 고르기).
        auto_var = st.toggle("추천 변수 (상관 높은 조합 자동)", value=True, key="sv_auto",
                             help="켜져 있으면 이 분류 단계에서 우상향(질↑=멀티플↑) "
                                  "상관이 가장 높은 X·Y 조합을 자동으로 씁니다. "
                                  "끄면 아래에서 직접 고르는 수동 설정이 됩니다.")
        if not auto_var:
            y_label3 = st.selectbox("Y축 (멀티플)", list(MULTIPLES), index=1, key="sv_y")
            x_label3 = st.selectbox("X축", list(X_AXES), index=0, key="sv_x")

        # ---- 추천 조합 계산: 자동 모드의 변수 선택 + 수동 모드의 추천 안내 ----
        best_combo = ("", "", -1.0)
        for _xl, _xc in X_AXES.items():
            for _yl, _yc in MULTIPLES.items():
                _dd = df[df[_xc].notna() & df[_yc].notna() & (df[_yc] > 0)]
                if len(_dd) < 10:
                    continue
                _xlo, _xhi = _dd[_xc].quantile([0.01, 0.99])
                _yhi = _dd[_yc].quantile(0.99)
                _dd = _dd[(_dd[_xc] >= _xlo) & (_dd[_xc] <= _xhi) & (_dd[_yc] <= _yhi)]
                _g = (_dd.groupby(lvl_col3)
                      .agg(x=(_xc, "mean"), y=(_yc, "mean"), n=(_xc, "size")))
                _g = _g[_g["n"] >= min_n]
                if fix_out:
                    _g = drop_iqr(_g, "x", "y")
                _r = signed_r(_g["x"], _g["y"])
                if not np.isnan(_r) and _r > best_combo[2]:
                    best_combo = (_xl, _yl, _r)

        if auto_var:
            if best_combo[2] > 0:
                x_label3, y_label3 = best_combo[0], best_combo[1]
                st.info(f"🤖 **자동 선택**: X **{x_label3}** · Y **{y_label3}** "
                        f"(R = {best_combo[2]:.2f}) — 이 분류에서 우상향 상관이 "
                        "가장 높은 조합입니다.")
            else:
                x_label3, y_label3 = "ROIC+SG", "EV/Sales"
                st.info("우상향 상관 조합이 없어 기본값 X ROIC+SG · Y EV/Sales를 "
                        "사용합니다. 수동 설정으로 바꿔서 직접 골라보세요.")

        st.markdown("##### 🎯 주요조건 입력")
        # 섹터 탭에서는 조건이 '그룹 평균'에 적용된다 (멀티플 조건이 먼저)
        y_max3 = st.number_input(f"{y_label3} 평균 이하", value=DEFAULT_Y_MAX[y_label3] * 2,
                                 step=0.5, key=f"sv_ymax_{MULTIPLES[y_label3]}",
                                 help="그룹 평균은 개별 종목보다 높게 나오는 경향이 있어 "
                                      "기본값을 종목 기준의 2배로 넉넉하게 잡았습니다.")
        x_min3 = st.number_input(f"{x_label3} 평균 이상 (%)", value=0.0, step=1.0,
                                 key="sv_xmin") / 100

    x_col, y_col = X_AXES[x_label3], MULTIPLES[y_label3]
    clicked3 = None
    d3 = df[df[x_col].notna() & df[y_col].notna() & (df[y_col] > 0)].copy()
    # 평균 왜곡 방지: 극단값(상하위 1%) 제외 후 그룹 평균
    x_lo, x_hi = d3[x_col].quantile([0.01, 0.99])
    y_hi = d3[y_col].quantile(0.99)
    d3 = d3[(d3[x_col] >= x_lo) & (d3[x_col] <= x_hi) & (d3[y_col] <= y_hi)]
    grp = (d3.groupby(lvl_col3)
           .agg(x=(x_col, "mean"), y=(y_col, "mean"), n=(x_col, "size"))
           .reset_index().rename(columns={lvl_col3: "그룹"}))
    n_all = len(grp[grp["n"] >= min_n])
    grp = grp[(grp["n"] >= min_n) & (grp["x"] > x_min3)
              & (grp["y"] < y_max3)].reset_index(drop=True)

    # 극단값 그룹 감지 (IQR 규칙): 평균이 유독 동떨어진 그룹은 추세선을 왜곡한다
    n_out = 0
    if len(grp) >= 5:
        q1y, q3y = grp["y"].quantile([0.25, 0.75])
        iqr_y = q3y - q1y
        q1x, q3x = grp["x"].quantile([0.25, 0.75])
        iqr_x = q3x - q1x
        out_mask = ((grp["y"] > q3y + 1.5 * iqr_y) | (grp["y"] < q1y - 1.5 * iqr_y)
                    | (grp["x"] > q3x + 1.5 * iqr_x) | (grp["x"] < q1x - 1.5 * iqr_x))
        n_out = int(out_mask.sum())
        if fix_out and n_out:
            grp = grp[~out_mask].reset_index(drop=True)

    trend3 = None
    if len(grp) >= 3 and grp["x"].std() > 0:
        slope3, icept3 = np.polyfit(grp["x"], grp["y"], 1)
        grp["추세대비"] = (grp["y"] - (slope3 * grp["x"] + icept3)).round(2)
        xs = pd.DataFrame({"x": [float(grp["x"].min()), float(grp["x"].max())]})
        xs["y"] = slope3 * xs["x"] + icept3
        trend3 = alt.Chart(xs).mark_line(color="#d43a2f", strokeDash=[5, 4],
                                         size=2, opacity=0.9).encode(x="x", y="y")
    else:
        grp["추세대비"] = np.nan

    # 챔피언: 질(X 평균)이 그룹들 중앙값 이상이면서 추세선 대비 가장 아래
    champ = None
    if grp["추세대비"].notna().any():
        cand = grp[grp["x"] >= grp["x"].median()]
        champ = (cand if not cand.empty else grp).sort_values("추세대비").iloc[0]

    with c1:
        if fix_out and n_out:
            _note = f" · 극단값 {n_out}개 제외됨"
        elif n_out:
            _note = f" · ⚠️ 극단값 의심 {n_out}개 (위 토글로 제외 가능)"
        else:
            _note = ""
        st.markdown(f"**그룹 {n_all}개 중 조건 통과 {len(grp)}개**{_note}")

        if not auto_var:
            if best_combo[2] > 0:
                st.info(f"💡 **추천 조합**: 이 분류 단계에서는 "
                        f"**X {best_combo[0]} · Y {best_combo[1]}** 조합이 우상향 관계로 "
                        f"설명력이 가장 높습니다 (R = {best_combo[2]:.2f}). "
                        "직접 바꾸거나 위의 '추천 변수' 토글을 켜면 자동 적용됩니다.")
            else:
                st.info("💡 이 분류 단계에서는 우상향(질↑=멀티플↑) 관계를 보이는 조합이 "
                        "없습니다 — 추세선 해석에 주의하세요.")

    with c2:
        if grp.empty:
            st.info("표시할 그룹이 없습니다. 조건을 완화하거나 최소 종목 수를 낮춰보세요.")
        else:
            try:
                dark = st.context.theme.type == "dark"
            except Exception:
                dark = False
            # 점 클릭 → 아래 드릴다운이 그 섹터로 바뀐다
            sel_pt = alt.selection_point(name="sector_click", fields=["그룹"],
                                         on="click", empty=False)
            base3 = alt.Chart(grp).add_params(sel_pt).mark_circle(
                opacity=0.8, color=C_MATCH).encode(
                x=alt.X("x", title=f"{x_label3} 평균 (높을수록 좋은 그룹)",
                        axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
                y=alt.Y("y", title=f"{y_label3} 평균 (낮을수록 싼 그룹)",
                        scale=alt.Scale(zero=False)),
                size=alt.Size("n", title="종목 수", scale=alt.Scale(range=[80, 700])),
                tooltip=[alt.Tooltip("그룹"), alt.Tooltip("n", title="종목 수"),
                         alt.Tooltip("x", title=f"{x_label3} 평균", format=".1%"),
                         alt.Tooltip("y", title=f"{y_label3} 평균", format=".2f"),
                         alt.Tooltip("추세대비", title="추세선 대비 (음수=선 아래)",
                                     format="+.2f")])
            lbl3 = alt.Chart(grp).mark_text(
                dy=-13, fontSize=12, fontWeight="bold",
                color="#9ecbff" if dark else "#1a5cad").encode(x="x", y="y", text="그룹")
            layers3 = [base3, lbl3]
            if trend3 is not None:
                layers3.append(trend3)
            if champ is not None:
                cd = grp[grp["그룹"] == champ["그룹"]]
                layers3.append(alt.Chart(cd).mark_point(
                    shape="diamond", size=420, filled=True, color=C_PICK,
                    stroke="white", strokeWidth=1.5).encode(x="x", y="y"))
            # key가 설정 값에 따라 바뀌게 해서, 변수/조건을 바꾸면 확대·이동 상태가
            # 초기화돼 항상 잘 보이는 화면으로 시작한다 (같은 설정에서는 드래그 유지)
            chart_key = f"sv_chart_{lvl_col3}_{x_col}_{y_col}_{x_min3}_{y_max3}_{min_n}"
            ev3 = st.altair_chart(alt.layer(*layers3).properties(height=620).interactive(),
                                  use_container_width=True,
                                  on_select="rerun", key=chart_key)
            try:
                pts = ev3["selection"]["sector_click"]
                if pts:
                    clicked3 = pts[0]["그룹"]
            except Exception:
                pass
            st.caption("💡 점을 **클릭**하면 아래 '섹터 안 들여다보기'가 그 섹터로 바뀝니다.")

    rec_clicked = None
    if champ is not None:
        st.divider()
        st.markdown(f"#### 🏆 이번 주 추천 섹터 — {lvl_label3} 기준")
        st.markdown(
            f"**{champ['그룹']}** — {x_label3} 평균 **{champ['x']:.1%}**, "
            f"{y_label3} 평균 **{champ['y']:.2f}배**, 추세선 대비 **{champ['추세대비']:+.2f}** "
            f"(종목 {int(champ['n'])}개). 질이 그룹 평균 이상이면서, 같은 질 대비 "
            f"멀티플이 가장 낮게(=싸게) 거래되는 그룹입니다.")
        # 추천 리스트: 추세선 대비 싸게 거래되는 순서 상위 10개 — 행을 클릭하면
        # 아래 '섹터 안 들여다보기'가 그 섹터로 바뀐다
        rec = grp.sort_values("추세대비").head(10).copy()
        rec_disp = pd.DataFrame({
            "그룹": rec["그룹"].values,
            "종목 수": rec["n"].astype(int).values,
            f"{x_label3} 평균 (%)": (rec["x"] * 100).round(1).values,
            f"{y_label3} 평균": rec["y"].round(2).values,
            "추세선 대비 (음수=싸다)": rec["추세대비"].values,
        })
        st.caption("추세선 대비 싼 순서 상위 10개 — **행을 클릭**하면 아래 "
                   "'섹터 안 들여다보기'가 그 섹터로 바뀝니다.")
        ev_rec = st.dataframe(rec_disp, hide_index=True, use_container_width=True,
                              on_select="rerun", selection_mode="single-row",
                              key=f"sv_rec_{lvl_col3}")
        try:
            rows = ev_rec["selection"]["rows"]
            if rows:
                rec_clicked = rec_disp.iloc[rows[0]]["그룹"]
        except Exception:
            pass

    if not grp.empty:
        st.divider()
        st.markdown("#### 🔎 섹터 안 들여다보기 — 해당 섹터의 종목들")
        order = grp.sort_values("추세대비")["그룹"].tolist() if grp["추세대비"].notna().any() \
            else grp["그룹"].tolist()
        default = champ["그룹"] if champ is not None else order[0]
        # 차트 점 클릭 / 추천 리스트 행 클릭 → 그 섹터로 동기화.
        # (선택 상태는 rerun마다 남아 있으므로 '방금 바뀐 쪽'만 반영한다)
        if clicked3 in order and clicked3 != st.session_state.get("_sv_chart_prev"):
            st.session_state["_sv_chart_prev"] = clicked3
            st.session_state["sv_pick"] = clicked3
        if rec_clicked in order and rec_clicked != st.session_state.get("_sv_rec_prev"):
            st.session_state["_sv_rec_prev"] = rec_clicked
            st.session_state["sv_pick"] = rec_clicked
        if st.session_state.get("sv_pick") not in order:
            st.session_state["sv_pick"] = default
        d1, d2 = st.columns([1, 3.2], gap="large")
        with d1:
            sel3 = st.selectbox("섹터 선택 (추세선 대비 싼 순서)", order, key="sv_pick",
                                help="위 차트의 점을 클릭해도 선택됩니다.")
            sub3 = df[df[lvl_col3] == sel3]

            # 이 섹터 종목들만 놓고 다시 고르는 주요변수 — 섹터 평균에서 좋았던
            # 조합이 개별 섹터 안에서는 우하향일 수 있어서 따로 추천한다
            st.markdown("##### 📌 주요변수 선택")
            dd_auto = st.toggle("추천 변수 (상관 높은 조합 자동)", value=True,
                                key="sv_dd_auto",
                                help="이 섹터 종목들 사이에서 우상향 상관이 가장 높은 "
                                     "X·Y 조합을 자동으로 씁니다. 끄면 직접 선택.")
            if not dd_auto:
                dy_label = st.selectbox("Y축 (멀티플)", list(MULTIPLES), index=1,
                                        key="sv_dd_y")
                dx_label = st.selectbox("X축", list(X_AXES), index=0, key="sv_dd_x")
            dd_out = st.toggle("극단값 제외 (추세선 보정)", value=False, key="sv_dd_outlier",
                               help="동떨어진 종목(IQR 기준)을 차트와 추세선에서 빼서 "
                                    "추세선이 극단값에 눌리지 않게 합니다.")
            dbx, dby, dbr = best_relationship(sub3, drop_outliers=dd_out)
            if dd_auto:
                if dbr > 0:
                    dx_label, dy_label = dbx, dby
                    st.info(f"🤖 **자동 선택**: X **{dbx}** · Y **{dby}** "
                            f"(R = {dbr:.2f}) — 이 섹터 안에서 우상향 상관이 "
                            "가장 높은 조합입니다.")
                else:
                    dx_label, dy_label = x_label3, y_label3
                    st.info("이 섹터 안에는 우상향 상관 조합이 없어 위 섹터 차트와 "
                            "같은 변수를 사용합니다 — 추세선 해석에 주의하세요.")
            elif dbr > 0:
                st.info(f"💡 **추천 조합**: 이 섹터에서는 **X {dbx} · Y {dby}** "
                        f"(R = {dbr:.2f})가 우상향으로 설명력이 가장 높습니다.")

            st.markdown("##### 🎯 주요조건 입력")
            dy_max = st.number_input(f"{dy_label} 이하", value=DEFAULT_Y_MAX[dy_label],
                                     step=0.5, key=f"sv_dd_ymax_{MULTIPLES[dy_label]}")
            dx_min = st.number_input(f"{dx_label} 이상 (%)", value=0.0, step=5.0,
                                     key="sv_dd_xmin") / 100
        dx_col, dy_col = X_AXES[dx_label], MULTIPLES[dy_label]
        valid3 = sub3[sub3[dx_col].notna() & (sub3[dx_col] > dx_min)
                      & (sub3[dy_col] > 0) & (sub3[dy_col] < dy_max)]
        with d1:
            st.markdown(f"**{sel3} {len(sub3)}개 중 조건 통과 {len(valid3)}개**")
        with d2:
            st.altair_chart(scatter(sub3, dx_col, dy_col, dx_label, dy_label,
                                    dx_min, dy_max, label_matches=True,
                                    drop_outliers=dd_out),
                            use_container_width=True)
        st.markdown(f"##### {sel3} 종목 순위 — '좋은데 싼' 점수순 ({len(valid3)}개)")
        st.caption("점수 = 그룹 안에서 질(X) 백분위와 멀티플 낮음(Y) 백분위의 평균 (100점 만점). "
                   "높을수록 '질 대비 싸다'는 뜻입니다.")
        match_table(valid3, dx_col, dy_col, dx_label, dy_label, key="dl_sector", score=True)

st.divider()
st.caption("차트에는 **조건을 통과한 종목만** 표시됩니다 (티커 조회에서는 선택한 종목도 함께). · "
           "🔵 파란 점 = 2026년 추정치 기준 멀티플, 🟡 노란 점 = 2026년 추정치가 없어서 "
           "LTM(최근 4개 분기 실적)으로 대체된 종목입니다. EV는 두 경우 모두 현재 값입니다. "
           "PBR은 항상 현재 장부가, EV/FCF는 항상 LTM 기준(FCF는 추정치가 거의 없음). · "
           "🔴 빨간 점선 = 추세선: 표시된 종목들 기준 '질이 이 정도면 보통 이 가격' 이라는 평균선입니다. "
           "점이 선보다 **아래**에 있으면 같은 질 대비 싸게 거래된다는 뜻 (마우스를 올리면 '추세선 대비' 값이 음수). · "
           "데이터: Capital IQ 기반 비교기업 워크북에서 추출 · 멀티플이 0 이하(적자 등)인 종목은 "
           "조건 검색에서 제외됩니다 · 차트는 보기 좋게 극단값(상하위 1%)을 잘라서 그립니다.")
