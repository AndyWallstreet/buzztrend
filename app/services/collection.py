"""Collection orchestration: run collectors and upsert daily counts.

Mock mode: every channel returns a direct daily count.
Real mode: YouTube/Reddit return true per-day figures; Naver only exposes an
all-time total, so we store it as a snapshot and derive the daily count as the
delta between consecutive snapshots (first day has no delta yet).
"""
import logging
from datetime import date as date_cls

from sqlalchemy.orm import Session

from .. import config
from ..collectors import get_collectors
from ..models import BuzzDaily, BuzzSnapshot, Keyword

log = logging.getLogger("buzztrend.collection")

SNAPSHOT_CHANNELS = {"naver_blog", "naver_news", "naver_cafe"}


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


def _snapshot_delta(session: Session, keyword_id: int, channel: str,
                    day: date_cls, total: int) -> int | None:
    """Store today's all-time total; return the daily delta if computable."""
    snap = (session.query(BuzzSnapshot)
            .filter_by(keyword_id=keyword_id, channel=channel, date=day)
            .one_or_none())
    if snap is None:
        session.add(BuzzSnapshot(keyword_id=keyword_id, channel=channel,
                                 date=day, total=total))
    else:
        snap.total = total

    prev = (session.query(BuzzSnapshot)
            .filter(BuzzSnapshot.keyword_id == keyword_id,
                    BuzzSnapshot.channel == channel,
                    BuzzSnapshot.date < day)
            .order_by(BuzzSnapshot.date.desc())
            .first())
    if prev is None:
        return None  # first snapshot — delta from tomorrow
    return max(0, total - prev.total)


def collect_for_day(session: Session, day: date_cls, collectors=None) -> int:
    """Collect every active keyword across all channels for `day`.

    Returns the number of (keyword, channel) points written.
    """
    collectors = collectors if collectors is not None else get_collectors()
    keywords = session.query(Keyword).filter_by(active=True).all()
    written = 0
    for kw in keywords:
        for col in collectors:
            try:
                value = col.fetch(kw.term, day)
            except Exception as exc:  # one bad channel shouldn't kill the run
                log.warning("collect failed term=%s channel=%s: %s",
                            kw.term, col.channel, exc)
                continue
            if not config.USE_MOCK and col.channel in SNAPSHOT_CHANNELS:
                count = _snapshot_delta(session, kw.id, col.channel, day, value)
                if count is None:
                    log.info("first snapshot term=%s channel=%s total=%d "
                             "(daily counts start tomorrow)",
                             kw.term, col.channel, value)
                    continue
            else:
                count = value
            upsert_count(session, kw.id, col.channel, day, count)
            written += 1
    session.commit()
    log.info("collected %d points for %s", written, day)
    return written
