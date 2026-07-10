"""Small CLI for one-off operations without the web server.

    python cli.py seed          # (re)generate mock history
    python cli.py collect       # collect today's counts + check alerts
    python cli.py add "keyword"
    python cli.py list
"""
import sys
from datetime import date

from app.database import init_db, session_scope
from app.models import Keyword
from app.services.alerts import check_alerts
from app.services.collection import collect_for_day
from app.services.seed import ensure_default_keywords, seed_history


def main(argv):
    init_db()
    cmd = argv[0] if argv else "help"

    if cmd == "seed":
        with session_scope() as s:
            ensure_default_keywords(s)
            seed_history(s)
        print("seeded.")
    elif cmd == "collect":
        with session_scope() as s:
            n = collect_for_day(s, date.today())
            a = check_alerts(s, date.today())
        print(f"collected {n} points, {a} new alerts.")
    elif cmd == "add" and len(argv) > 1:
        with session_scope() as s:
            if not s.query(Keyword).filter_by(term=argv[1]).first():
                s.add(Keyword(term=argv[1]))
        print(f"added '{argv[1]}'. Run `python cli.py seed` to backfill history.")
    elif cmd == "list":
        with session_scope() as s:
            for k in s.query(Keyword).all():
                print(f"  [{k.id}] {k.term} {'' if k.active else '(inactive)'}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
