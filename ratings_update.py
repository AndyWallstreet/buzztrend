"""실관람객 평점(CGV 에그지수) + 댓글 긍부정 비율을 매일 한 줄씩 쌓는다.

에그지수는 CGV 무비차트에 표시되는 값으로, **표를 산 사람만** 매길 수 있어서
실관람객 만족도에 가장 가까운 공개 숫자다. CGV는 파이썬 요청을 403으로 막으므로
숫자는 Browser pane 에서 긁어 JSON 으로 넘겨받는다 (유튜브 수집과 같은 방식).

댓글 긍부정은 이미 있는 5단계 분류(sentiment.json)의 그날 스냅샷을 비율로 바꿔
`sentiment_daily.csv` 에 쌓는다 — 개봉 후 분위기가 꺾이는지 추세로 보기 위함.

사용법:
  python ratings_update.py <scrape.json>          # 수집값 반영 + 사이트 파일 + push
  python ratings_update.py <scrape.json> --no-push

scrape.json:
{
  "date": "2026-08-05",
  "cgv": {"egg": 96, "rate": 7.0, "cum_text": "2.7만"},
  "peers": [{"name": "미니언즈 & 몬스터즈", "egg": 94}, ...]      # 선택
}
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).parent
DATA = REPO / "data" / "hatchuping"

M2_OPEN = date(2026, 8, 5)
RATINGS = DATA / "ratings.csv"
SENT_DAILY = DATA / "sentiment_daily.csv"
RATINGS_HEAD = ["date", "day", "cgv_egg", "cgv_rate", "cgv_cum_text"]
SENT_HEAD = ["date", "day", "strong_pos", "pos", "neu", "neg", "strong_neg",
             "total", "pos_ratio", "neg_ratio"]


def upsert(path: Path, head: list[str], row: dict):
    """같은 날짜 행이 있으면 덮어쓰고, 없으면 넣는다 (하루 여러 번 돌려도 안전)."""
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").strip().split("\n")[1:]:
            p = line.split(",")
            if p and p[0]:
                rows[p[0]] = dict(zip(head, p))
    before = rows.get(row["date"])
    rows[row["date"]] = {h: row.get(h, "") for h in head}
    lines = [",".join(head)]
    for k in sorted(rows):
        lines.append(",".join(str(rows[k].get(h, "")) for h in head))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{path.name}: {'덮어씀' if before else '추가'} {row['date']} -> "
          + ", ".join(f"{h}={row.get(h)}" for h in head[2:]))


def main():
    scrape = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = date.fromisoformat(scrape["date"])
    day = (d - M2_OPEN).days

    # ---- 1. CGV 에그지수
    cgv = scrape.get("cgv") or {}
    if cgv.get("egg") is not None:
        upsert(RATINGS, RATINGS_HEAD, {
            "date": d.isoformat(), "day": day,
            "cgv_egg": cgv["egg"], "cgv_rate": cgv.get("rate", ""),
            "cgv_cum_text": cgv.get("cum_text", "")})
    else:
        print("cgv 에그지수 없음 — ratings.csv 건너뜀")

    # ---- 2. 댓글 긍부정 비율 (sentiment.json 스냅샷 → 하루 한 줄)
    sp = DATA / "sentiment.json"
    if sp.exists():
        sent = json.loads(sp.read_text(encoding="utf-8"))
        m2 = (sent.get("main") or {}).get("m2") or []
        if len(m2) == 5:
            total = sum(m2)
            if total:
                upsert(SENT_DAILY, SENT_HEAD, {
                    "date": d.isoformat(), "day": day,
                    "strong_pos": m2[0], "pos": m2[1], "neu": m2[2],
                    "neg": m2[3], "strong_neg": m2[4], "total": total,
                    "pos_ratio": round((m2[0] + m2[1]) / total, 4),
                    "neg_ratio": round((m2[3] + m2[4]) / total, 4)})
            else:
                print("sentiment 합계 0 — 건너뜀")
        else:
            print("sentiment.json main.m2 형식이 5개가 아님 — 건너뜀")

    # ---- 3. 참고용 또래 애니 에그지수 (기준선으로 화면에 표시)
    if scrape.get("peers"):
        (DATA / "ratings_peers.json").write_text(json.dumps({
            "as_of": d.isoformat(), "peers": scrape["peers"],
            "note": "CGV 무비차트 동시 수집 — 가족/애니 비교용"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ratings_peers.json: {len(scrape['peers'])}편")

    (DATA / "ratings_now.json").write_text(json.dumps({
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
        "date": d.isoformat(), "day": day, "cgv": cgv},
        ensure_ascii=False, indent=2), encoding="utf-8")

    if "--no-push" in sys.argv:
        return

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode == 0:
        git("add", "data/hatchuping")
        if git("commit", "-m", f"ratings update {d.isoformat()}").returncode == 0:
            git("pull", "--rebase")
            p = git("push")
            print("git push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])
        else:
            print("git: 새로 커밋할 것 없음")


if __name__ == "__main__":
    main()
