# -*- coding: utf-8 -*-
"""Amazon Tracker ④ 판매식 검증 탭 — 순위→개수 공식을 왜 이렇게 만들었고 얼마나 맞는지.

PM 2026-10-15: "3,000 의 기준은 뭐야?" 에 답하는 화면. 계산은 keepa_sales_calib.py 가 하고
(bsr_calib.json · bsr_calib_points*.csv), 여기서는 보여주기만 한다.
amazon_tracker.py 에서 render(c4, pts, vmk, sub, lab) 로 부른다.
"""
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st


def render(c4, pts, vmk, sub, lab):
    """c4 = bsr_calib.json 의 한 시장 dict · pts = 검증 점 DataFrame · vmk = '미국'/'일본'."""
    if not c4 or pts is None or not len(pts):
        st.info("검증 자료가 없습니다. `python keepa_sales_calib.py` 를 먼저 돌려주세요.")
        return
    knot = int(c4.get("knot_rank", 3000))
    a_, bt, ba = c4["a"], c4["b_top"], c4["b_add"]

    sub("1. 왜 순위를 개수로 바꿔야 하나")
    st.markdown(
        "- **BSR 은 순위**입니다. 1위와 2위의 판매 차이와, 1,000위와 1,001위의 차이는 전혀 다릅니다. "
        "순위를 그냥 더하거나 평균 내면 뜻이 없습니다.\n"
        "- 아마존이 주는 실제 숫자는 **'지난달 X개 이상 구매'** 표시뿐입니다. 하지만 ① 2023-08 이후만 있고, "
        "② '10,000개 이상' 같은 **계단값(하한)** 이고, ③ 일부 상품(예: 메디큐브 1등 상품)에는 표시가 없습니다.\n"
        "- 그래서 **순위 → 개수 공식**이 필요하고, 그 공식이 맞는지는 **실제 표시와 비교해서** 확인합니다. "
        "이 탭이 그 확인 결과입니다.")

    sub("2. 어떤 자료로 확인했나")
    m0, m1 = c4.get("months", ["", ""])
    st.markdown(
        f"- **{vmk} 아마존 · 상품-월 {c4['n_points']:,}개** (상품 {c4['n_asin']}개 · 브랜드 "
        f"{c4.get('n_brands', '–')}개 · {m0} ~ {m1}). 한 점 = 한 상품의 한 달: 그 달 **순위 중앙값**과 "
        "아마존 **판매 표시 중앙값**.\n"
        "- 뺀 것: 한 달에 20일 미만 기록된 달 · **순위를 공유하는 상품**(용량·색상 묶음은 순위는 하나인데 "
        "표시는 상품마다 따로라 기울기를 낮춤) · Keepa 브랜드 칸이 안 맞는 상품.")

    sub("3. 실제 점과 두 공식", "가로 = 순위 (로그) · 세로 = 아마존 표시 판매 (로그) · 점 = 상품-월")
    p4 = pts[(pts["rank_median"] > 0) & (pts["sold"] > 0)].copy()
    p4["브랜드"] = p4["brand"].map(lab)
    grid = pd.DataFrame({"rank": np.logspace(0, np.log10(max(p4["rank_median"].max() * 1.5, 1e5)), 120)})
    lg = np.log10(grid["rank"])
    grid["B 두 구간"] = 10 ** (a_ + bt * lg + ba * np.maximum(lg - np.log10(knot), 0))
    la, lb = np.polyfit(np.log10(p4["rank_median"]), np.log10(p4["sold"]), 1)   # A: json 엔 지수만 있어 다시 맞춤
    grid["A 직선 하나"] = 10 ** (lb + la * lg)
    gl = grid.melt("rank", var_name="공식", value_name="sold")
    dots = alt.Chart(p4).mark_circle(size=22, opacity=0.45).encode(
        x=alt.X("rank_median:Q", title="월 순위 중앙값 (로그)", scale=alt.Scale(type="log")),
        y=alt.Y("sold:Q", title="아마존 표시: 지난달 X개 이상 (로그)", scale=alt.Scale(type="log")),
        color=alt.Color("브랜드:N", legend=alt.Legend(orient="right", columns=1, labelLimit=160)),
        tooltip=["브랜드:N", "month:N", alt.Tooltip("rank_median:Q", format=",.0f", title="순위"),
                 alt.Tooltip("sold:Q", format=",.0f", title="표시 판매")])
    lines = alt.Chart(gl).mark_line(size=2.5, color="#e8c15a").encode(
        x="rank:Q", y="sold:Q",
        strokeDash=alt.StrokeDash("공식:N", scale=alt.Scale(domain=["B 두 구간", "A 직선 하나"],
                                                           range=[[1, 0], [6, 4]]),
                                  legend=alt.Legend(orient="top", title=None)))
    kr = alt.Chart(pd.DataFrame({"k": [knot]})).mark_rule(color="#e05252", strokeDash=[4, 3]).encode(x="k:Q")
    st.altair_chart((dots + lines + kr).properties(height=440), use_container_width=True)
    st.caption(f"노란 실선 = B(두 구간), 노란 점선 = A(직선 하나), 빨간 점선 = {knot:,}위. "
               f"왼쪽({knot:,}위 안쪽)은 점들이 거의 평평하고 오른쪽은 가파르게 떨어집니다 — 직선 하나로는 "
               "한쪽이 반드시 틀립니다. 세로 값이 계단처럼 보이는 건 아마존 표시가 '○개 이상' 단위이기 때문입니다.")

    sub(f"4. 왜 {knot:,}위에서 꺾나", "① 구간별 기울기 → 어디서 바뀌는지 · ② 꺾임 위치를 바꿔 가며 점수")
    q1, q2 = st.columns(2)
    with q1:
        bd = pd.DataFrame(c4.get("bands", []))
        if len(bd):
            bd["순위 구간"] = bd.apply(lambda r: f"{int(r.lo):,} ~ {int(r.hi):,}위" if r.hi < 10 ** 6
                                   else f"{int(r.lo):,}위 이상", axis=1)
            st.markdown("**① 순위 구간별 기울기** — 순위가 10배 나빠질 때 판매가 몇 배 줄어드나 "
                        "(기울기 1 = 10배 · 0.2 = 1.6배)")
            st.dataframe(bd[["순위 구간", "n", "slope", "sold_median"]].rename(
                columns={"n": "점 수", "slope": "기울기", "sold_median": "표시 판매 중앙값"}),
                hide_index=True, use_container_width=True)
            st.caption(f"{knot:,}위를 경계로 기울기가 확 바뀝니다. 처음엔 이 표를 보고 눈으로 {knot:,}을 골랐습니다.")
    with q2:
        sc = pd.DataFrame(c4.get("knot_scan", []))
        if len(sc):
            best = int(sc.loc[sc["within_2x"].idxmax(), "knot"])
            st.markdown("**② 꺾임 위치를 바꿔 가며 점수** — 브랜드 하나를 빼고 공식을 만든 뒤 그 브랜드로 채점(C)")
            scc = alt.Chart(sc).mark_line(point=True, color="#8ec9ff").encode(
                x=alt.X("knot:Q", title="꺾임 위치 (순위, 로그)", scale=alt.Scale(type="log")),
                y=alt.Y("within_2x:Q", title="실제 표시의 2배 안에 든 비율", axis=alt.Axis(format="%"),
                        scale=alt.Scale(domain=[0.4, 0.9])),
                tooltip=[alt.Tooltip("knot:Q", format=",.0f", title="꺾임"),
                         alt.Tooltip("within_2x:Q", format=".0%", title="2배 안"),
                         alt.Tooltip("median_err_x:Q", format=".2f", title="중간 오차(배)")])
            st.altair_chart((scc + kr).properties(height=260), use_container_width=True)
            same = best == knot
            st.caption(f"데이터로 가장 좋은 위치 = **{best:,}위**"
                       + (f" (쓰는 값 {knot:,}위와 같음)" if same else
                          f" · 쓰는 값 {knot:,}위와의 차이는 1%p 안 — 두 시장을 같은 기준으로 두려고 {knot:,}을 유지")
                       + ". 2,000~5,000 사이는 거의 같고, 그 밖은 뚜렷이 나빠집니다.")

    sub("5. 공식 점수 — A · B · C", "합격 기준(제가 정함): 실제 표시의 2배 안 70% 이상 · 중간 오차 1.5배 이하")
    score = pd.DataFrame([
        {"공식": "A. 직선 하나 (예전)", "설명": "1위~100만 위까지 규칙 하나",
         "2배 안": c4.get("linear_within_2x"), "중간 오차(배)": c4.get("linear_median_err_x")},
        {"공식": f"B. 두 구간 ({knot:,}위 꺾임)", "설명": "18개 브랜드로 만들고 같은 브랜드로 채점",
         "2배 안": c4.get("within_2x"), "중간 오차(배)": c4.get("median_err_x")},
        {"공식": "C. B 를 처음 보는 브랜드에", "설명": "브랜드 하나를 빼고 만든 뒤 그 브랜드로 채점 (브랜드 수만큼 반복)",
         "2배 안": c4.get("lbo_within_2x"), "중간 오차(배)": c4.get("lbo_median_err_x")},
    ])
    score["판정"] = np.where((score["2배 안"] >= 0.7) & (score["중간 오차(배)"] <= 1.5), "합격", "불합격")
    score["2배 안"] = score["2배 안"].map("{:.0%}".format)
    st.dataframe(score, hide_index=True, use_container_width=True)
    st.markdown(
        "- **A → B 는 공식을 고친 것**, **B → C 는 공식은 그대로 두고 시험을 엄격하게 본 것**입니다.\n"
        "- C 가 B 와 거의 같다는 게 핵심입니다: 공식이 특정 브랜드를 외운 게 아니라 **새 브랜드에도 통한다**는 뜻입니다.\n"
        f"- 지금 쓰는 공식: 판매 = 10^({a_:.2f} − {-bt:.2f}·log순위 − {-ba:.2f}·max(log순위 − log{knot:,}, 0)). "
        f"즉 {knot:,}위 안쪽 기울기 {c4.get('slope_top')}, 바깥 {c4.get('slope_tail')}. "
        f"1,000위 ≈ 월 {c4.get('sold_at_rank_1000', 0):,}개 · 100위 ≈ {c4.get('sold_at_rank_100', 0):,}개."
        + (" 일본은 안쪽 기울기가 살짝 양수(순위가 나빠질수록 더 판다는 뜻)로 나와 0 으로 고정했습니다."
           if vmk == "일본" else ""))

    sub("6. 브랜드별 치우침", "모델 ÷ 실제 의 중앙값 · 1 = 정확 · 0.5 = 절반으로 작게 · 2 = 두 배로 크게")
    bb = pd.DataFrame(c4.get("brand_bias", []))
    if len(bb):
        bb["브랜드"] = bb["brand"].map(lab)
        bb["읽는법"] = np.where(bb["ratio"] < 0.67, "실제보다 작게 봄",
                             np.where(bb["ratio"] > 1.5, "실제보다 크게 봄", "대체로 맞음"))
        bars = alt.Chart(bb).mark_bar().encode(
            x=alt.X("ratio:Q", title="모델 ÷ 실제 (로그)", scale=alt.Scale(type="log", domain=[0.1, 10])),
            y=alt.Y("브랜드:N", sort="-x", title=None),
            color=alt.Color("읽는법:N", scale=alt.Scale(domain=["실제보다 작게 봄", "대체로 맞음", "실제보다 크게 봄"],
                                                     range=["#8ec9ff", "#3fb27f", "#eb6834"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["브랜드:N", alt.Tooltip("ratio:Q", format=".2f", title="모델÷실제"),
                     alt.Tooltip("n:Q", title="점 수")])
        one = alt.Chart(pd.DataFrame({"x": [1]})).mark_rule(color="#dde5f0").encode(x="x:Q")
        st.altair_chart((bars + one).properties(height=26 * len(bb) + 40), use_container_width=True)
        st.caption("같은 순위여도 브랜드마다 파는 양이 다릅니다 (가격·묶음 크기·카테고리가 달라서). "
                   "그래서 **브랜드끼리 개수 비교는 아마존 표시값으로** 하고, 이 공식은 한 브랜드 안의 흐름과 "
                   "표시가 없는 곳을 채우는 데 씁니다.")

    sub("7. 한계 — 이 공식을 믿을 때 알아둘 것")
    st.markdown(
        "1. **검증의 자(척도) 자체가 거칩니다.** '10,000개 이상' 표시는 15,000개여도 10,000으로 나옵니다. "
        "위 점수는 이 거친 자로 잰 것입니다.\n"
        "2. **2023-08 이후 자료로만 확인했습니다.** 그 전 기간은 같은 공식이 맞는다고 가정하는 것입니다.\n"
        "3. **꺾임이 한 번뿐이라는 것도 가정입니다.** 부드러운 곡선이 실제에 더 가까울 수 있지만, 지금 자료 크기에서 "
        "더 복잡하게 만들면 새 브랜드에서 틀릴 위험이 커집니다.\n"
        "4. **'뷰티 & 퍼스널 케어 전체' 순위 기준입니다.** 세부 카테고리(페이스 모이스처라이저 등) 순위에는 다른 숫자가 "
        "맞습니다. 기사에 나오는 '○○ 부문 1위' 와 섞어 쓰면 안 됩니다.\n"
        f"5. **{knot:,}위 안쪽이 평평하다는 건 '개수' 이야기입니다.** 상위권 브랜드는 순위가 움직여도 개수 추정이 "
        "거의 안 변하므로, **타이밍(언제 올랐나)은 ② 주력 상품 순위 방식**으로 보는 게 낫습니다. "
        "또 1~10위처럼 맨 꼭대기는 검증 점이 적어 실제보다 작게 나올 수 있습니다.\n"
        "6. **브랜드 합계 지수는 추적 상품 수에 따라 달라집니다.** 상품을 많이 추적한 브랜드가 커 보입니다. "
        "브랜드끼리 크기 비교는 표시값으로 하세요.\n"
        "7. 합격 기준(2배 안 70%, 중간 오차 1.5배)은 제가 정한 것입니다. 더 엄격하게 잡으면 B 도 불합격입니다.")
