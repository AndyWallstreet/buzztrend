"""Collection orchestration: run collectors and upsert daily counts."""
import logging
from datetime import date as date_cls

from sqlalchemy.orm import Session

from ..collectors import get_collectors
from ..models import BuzzDaily, Keyword

log = logging.getLogger("buzztrend.collection")


def upsert_count(session: Session, keyword_id: int, channel: str,
                 day: date_cls, count: int) -> None:
    row = (session.query(BuzzDaily)
           .filter_by(keyword_id=keyword_id, channel=channel, date=day)
           .one_or_none())
    if row is None:
        session.add(BuzzDaily(keyword_id=keyword_id, channel=channel,
                              date=day, count=count))
    else:
        row.count = count


def collect_for_day(session: Session, day: date_cls, collectors=None) -> int:
    """Collect every active keyword across all channels for `day`.

    Returns the number of (keyword, channel) points written.
    """
    collectors = collectors or get_collectors()
    keywords = session.query(Keyword).filter_by(active=True).all()
    written = 0
    for kw in keywords:
        for col in collectors:
            try:
                count = col.fetch(kw.term, day)
            except Exception as exc:  # one bad channel shouldn't kill the run
                log.warning("collect failed term=%s channel=%s: %s",
                            kw.term, col.channel, exc)
                continue
            upsert_count(session, kw.id, col.channel, day, count)
            written += 1
    session.commit()
    log.info("collected %d points for %s", written, day)
    return written
