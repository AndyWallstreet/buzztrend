"""First-run seeding: default keywords + synthetic history + alert backfill."""
import logging
from datetime import date as date_cls, timedelta

from sqlalchemy.orm import Session

from .. import config
from ..collectors import mock_collectors
from ..models import Keyword
from .alerts import check_alerts
from .collection import collect_for_day

log = logging.getLogger("buzztrend.seed")


def ensure_default_keywords(session: Session) -> None:
    for term in config.DEFAULT_KEYWORDS:
        if not session.query(Keyword).filter_by(term=term).first():
            session.add(Keyword(term=term))
    session.commit()


def seed_history(session: Session, days: int | None = None) -> None:
    """Generate `days` of mock history for all keywords, then backfill alerts."""
    days = days or config.SEED_DAYS
    collectors = mock_collectors()  # history is always synthetic
    today = date_cls.today()

    for offset in range(days, -1, -1):
        collect_for_day(session, today - timedelta(days=offset), collectors)

    # Backfill alerts over the generated window.
    for offset in range(days, -1, -1):
        check_alerts(session, today - timedelta(days=offset))

    log.info("seeded %d days of history", days)


def add_keyword(session: Session, term: str, backfill: bool = True):
    """Add a keyword and (in mock mode) backfill its synthetic history + alerts.

    Returns the Keyword (existing or new), or None for an empty term.
    Shared by the FastAPI app and the Streamlit app.
    """
    term = (term or "").strip()
    if not term:
        return None
    existing = session.query(Keyword).filter_by(term=term).first()
    if existing:
        return existing

    kw = Keyword(term=term)
    session.add(kw)
    session.commit()

    if backfill and config.USE_MOCK:
        cols = mock_collectors()
        today = date_cls.today()
        for offset in range(config.SEED_DAYS, -1, -1):
            collect_for_day(session, today - timedelta(days=offset), cols)
        for offset in range(config.SEED_DAYS, -1, -1):
            check_alerts(session, today - timedelta(days=offset))
    return kw


def maybe_seed(session: Session) -> bool:
    """Seed on an empty DB. Returns True if seeding ran."""
    ensure_default_keywords(session)
    from ..models import BuzzDaily
    if session.query(BuzzDaily).first() is not None:
        return False
    seed_history(session)
    return True
