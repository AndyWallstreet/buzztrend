"""kbeauty tracker 실행 진입점. make 대신 사용:  python cli.py <명령>"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    p = argparse.ArgumentParser(description="K-Beauty 트래커 (PLAN.md 참고)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("import-oy", help="올리브영 수동 저장 파일 적재 (data/manual/oliveyoung/)")
    sub.add_parser("test", help="테스트 실행 (pytest)")
    for name, phase in [
        ("backfill", "Phase 1"), ("refresh", "Phase 1"), ("weekly", "Phase 4"),
        ("monthly", "Phase 4"), ("report", "Phase 4"), ("import-notes", "Phase 7"),
        ("publish", "Phase 7"),
    ]:
        sub.add_parser(name, help=f"아직 구현 전 ({phase})")

    args = p.parse_args()

    if args.cmd == "import-oy":
        from etl.oliveyoung_manual import import_all
        return import_all()
    if args.cmd == "test":
        return subprocess.call([sys.executable, "-m", "pytest", str(ROOT / "tests"), "-v"])

    print(f"'{args.cmd}' 명령은 아직 구현 전입니다. PLAN.md의 해당 Phase를 진행하면 생깁니다.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
