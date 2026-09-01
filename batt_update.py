# -*- coding: utf-8 -*-
"""2차전지 트래커 데이터 갱신 — batt-tracker 수집기를 돌리고 사이트 데이터로 복사.

Usage:
    python batt_update.py            # EIA+DART 수집 → 워크북 재생성 → 사이트 복사
    python batt_update.py --no-eia   # DART만
그 다음: git add data/batt && git commit && git push
"""
import shutil
import subprocess
import sys
from pathlib import Path

PY = sys.executable
TRACKER = Path(r"C:\Users\user99i1\batt-tracker")
DST = Path(__file__).resolve().parent / "data" / "batt"

subprocess.run([PY, "-X", "utf8", str(TRACKER / "fetch_data.py"),
                *sys.argv[1:]], check=True, cwd=TRACKER)
subprocess.run([PY, "-X", "utf8", str(TRACKER / "build_tracker.py")],
               check=True, cwd=TRACKER)
DST.mkdir(parents=True, exist_ok=True)
n = 0
for p in (TRACKER / "data").glob("*.csv"):
    shutil.copy(p, DST / p.name)
    n += 1
shutil.copy(TRACKER / "data" / "fetch_meta.json", DST / "fetch_meta.json")
print(f"사이트 데이터 복사 {n}개 → {DST}")
print("이제: git add data/batt && git commit -m 'batt update' && git push")
