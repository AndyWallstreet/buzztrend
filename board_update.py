# -*- coding: utf-8 -*-
"""네이버 종목토론방(SAMG엔터 419530) 일별 추적.

게시글 제목을 키워드로 긍/부정 분류해서
  - board_daily.csv   : 날짜별 글 수 · 긍정/부정/중립 수 · 비율
  - board_samples.json: 최근 이틀의 주요 긍정/부정 글 제목 (공감·조회 순)
을 쌓는다. 제목 기반 분류라 거칠다 — 화면에도 그렇게 적는다.

사용법:
  python board_update.py            # 수집 + 사이트 파일 + git push
  python board_update.py --no-push
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import truststore

truststore.inject_into_ssl()

REPO = Path(__file__).parent
DATA = REPO / "data" / "hatchuping"
CODE = "419530"                      # SAMG엔터
LOOKBACK_DAYS = 3                    # 오늘 포함 최근 3일치만 다시 집계
MAX_PAGES = 40

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Referer": f"https://finance.naver.com/item/main.naver?code={CODE}"}

# 종토방 말투 기준 키워드 — 영화 댓글 분류와 달리 주가 어휘로 잡는다.
POS = ["가즈아", "가즈", "상한가", "신고가", "급등", "상승", "오른다", "올라", "올랐",
       "돌파", "매수", "사자", "줍줍", "저평가", "대박", "흥행", "좋다", "좋아", "좋네",
       "기대", "축하", "익절", "수익", "간다", "갑시다", "달린다", "불기둥", "쏜다"]
NEG = ["폭락", "하락", "떨어", "내려", "물렸", "물림", "손절", "설거지", "고점", "꼭지",
       "망했", "망한", "별로", "실망", "매도", "팔아", "던져", "던진", "공매도", "하한가",
       "개미지옥", "조정", "속았", "사기", "거품", "나락", "손실", "빠진다", "음봉"]


def classify(title: str) -> str:
    p = any(k in title for k in POS)
    n = any(k in title for k in NEG)
    if p and not n:
        return "pos"
    if n and not p:
        return "neg"
    return "neu"


def fetch_posts(since: date):
    """since 이후의 글 (dt, title, views, agree, disagree) 목록."""
    posts, stop = [], False
    for page in range(1, MAX_PAGES + 1):
        r = requests.get(f"https://finance.naver.com/item/board.naver?code={CODE}&page={page}",
                         headers=H, timeout=30)
        r.encoding = "utf-8"
        # 셀 마크업이 행마다 조금씩 달라서 (new 아이콘, 프로필 등) 행 단위로 쪼개 파싱
        rows = []
        for chunk in r.text.split("<tr onMouseOver")[1:]:
            chunk = chunk.split("</tr>")[0]
            m_ts = re.search(r'<span class="tah p10 gray03">([\d.]+ [\d:]+)</span>', chunk)
            m_ti = re.search(r'board_read\.naver[^"]*"[^>]*title="([^"]*)"', chunk)
            if not (m_ts and m_ti):
                continue
            views = re.search(r'<td><span class="tah p10 gray03">([\d,]+)</span></td>', chunk)
            strongs = re.findall(r'<strong class="tah p10 gray03[^"]*">([\d,]+)</strong>', chunk)
            rows.append((m_ts.group(1), m_ti.group(1),
                         views.group(1) if views else "0",
                         strongs[0] if len(strongs) > 0 else "0",
                         strongs[1] if len(strongs) > 1 else "0"))
        if not rows:
            break
        for ts, title, views, agree, disagree in rows:
            dt = datetime.strptime(ts, "%Y.%m.%d %H:%M")
            if dt.date() < since:
                stop = True
                break
            posts.append({"dt": dt.isoformat(), "date": dt.date().isoformat(),
                          "title": title.strip(),
                          "views": int(views.replace(",", "")),
                          "agree": int(agree.replace(",", "")),
                          "disagree": int(disagree.replace(",", "")),
                          "sent": classify(title)})
        if stop:
            break
        time.sleep(0.6)              # 예의상 간격 (KOBIS 차단의 교훈)
    return posts


def main():
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS - 1)
    posts = fetch_posts(since)
    print(f"수집 {len(posts)}건 ({since} ~ {today})")
    if not posts:
        print("게시글 없음 — 종료")
        return

    # ---- board_daily.csv (같은 날짜 행은 덮어씀 — 오늘은 진행 중 스냅샷)
    head = ["date", "posts", "pos", "neg", "neu", "pos_ratio", "neg_ratio"]
    path = DATA / "board_daily.csv"
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").strip().split("\n")[1:]:
            p = line.split(",")
            if p and p[0]:
                rows[p[0]] = p
    for d in {p["date"] for p in posts}:
        day = [p for p in posts if p["date"] == d]
        pos = sum(1 for p in day if p["sent"] == "pos")
        neg = sum(1 for p in day if p["sent"] == "neg")
        neu = len(day) - pos - neg
        rows[d] = [d, str(len(day)), str(pos), str(neg), str(neu),
                   f"{pos / len(day):.4f}", f"{neg / len(day):.4f}"]
        print(f"  {d}: {len(day)}건 · 긍정 {pos} · 부정 {neg} · 중립 {neu}")
    path.write_text("\n".join([",".join(head)] + [",".join(rows[k]) for k in sorted(rows)])
                    + "\n", encoding="utf-8")

    # ---- 주요 글 (최근 이틀, 공감+조회 가중 순)
    def top(sent, n=6):
        pool = [p for p in posts if p["sent"] == sent]
        pool.sort(key=lambda p: (p["agree"] * 50 + p["views"]), reverse=True)
        return [{"date": p["date"], "title": p["title"], "views": p["views"],
                 "agree": p["agree"], "disagree": p["disagree"]} for p in pool[:n]]

    (DATA / "board_samples.json").write_text(json.dumps({
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
        "stock": "SAMG엔터 (419530)",
        "window": f"{since} ~ {today}",
        "top_pos": top("pos"), "top_neg": top("neg"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("board_samples.json written")

    if "--no-push" in sys.argv:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"naver board update {today.isoformat()}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
        else:
            print("git: 새로 커밋할 것 없음")


if __name__ == "__main__":
    main()
