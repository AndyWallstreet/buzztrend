"""First-run seeding + keyword management.

History generation is bulk-insert based so a full year across all channels
seeds in a couple of seconds (row-by-row upserts were far too slow at 365d).
"""
from __future__ import annotations

import logging
from datetime import date as date_cls, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from .. import config
from ..collectors.mock import mock_count
from ..models import AlertEvent, BuzzDaily, Keyword

log = logging.getLogger("buzztrend.seed")


def ensure_default_keywords(session: Session) -> None:
    for term in config.DEFAULT_KEYWORDS:
        if not session.query(Keyword).filter_by(term=term).first():
            session.add(Keyword(term=term))
    session.commit()


def backfill_alerts(session: Session, keyword_ids: list[int] | None = None) -> int:
    """Bulk spike detection over stored history (pandas rolling window)."""
    q = session.query(BuzzDaily)
    if keyword_ids:
        q = q.filter(BuzzDaily.keyword_id.in_(keyword_ids))
    rows = [(r.keyword_id, r.channel, r.date, r.count) for r in q.all()]
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=["kid", "channel", "day", "cnt"])

    existing = {(a.keyword_id, a.channel, a.date)
                for a in session.query(AlertEvent).all()}
    terms = {k.id: k.term for k in session.query(Keyword).all()}

    new = []
    for (kid, ch), g in df.groupby(["kid", "channel"]):
        g = g.sort_values("day").reset_index(drop=True)
        baseline = g["cnt"].rolling(7, min_periods=3).mean().shift(1)
        for i in range(len(g)):
            b = baseline.iloc[i]
            c = int(g["cnt"].iloc[i])
            d = g["day"].iloc[i]
            if pd.isna(b) or b <= 0 or c < 30:
                continue
            ratio = c / b
            if ratio < config.ALERT_SPIKE_RATIO or (kid, ch, d) in existing:
                continue
            label = config.CHANNELS_BY_KEY[ch]["label"]
            term = terms.get(kid, "?")
            new.append(AlertEvent(
                keyword_id=kid, channel=ch, date=d, count=c,
                baseline=round(float(b), 1), ratio=round(float(ratio), 2),
                message=(f"'{term}' 언급량이 {label}에서 7일 평균의 "
                         f"{ratio:.1f}배로 급증 ({c}건 vs 평균 ~{b:.0f}건)"),
            ))
    session.bulk_save_objects(new)
    session.commit()
    return len(new)


def seed_keyword_history(session: Session, kw: Keyword,
                         days: int | None = None) -> None:
    """(Re)generate mock history for one keyword — bulk, fast, idempotent."""
    days = days or config.SEED_DAYS
    session.query(BuzzDaily).filter_by(keyword_id=kw.id).delete()
    session.commit()

    today = date_cls.today()
    rows = []
    for ch in config.CHANNEL_KEYS:
        for off in range(days, -1, -1):
            d = today - timedelta(days=off)
            rows.append(BuzzDaily(keyword_id=kw.id, channel=ch, date=d,
                                  count=mock_count(kw.term, ch, d)))
    session.bulk_save_objects(rows)
    session.commit()
    backfill_alerts(session, [kw.id])


def seed_history(session: Session, days: int | None = None) -> None:
    for kw in session.query(Keyword).all():
        seed_keyword_history(session, kw, days)
    log.info("seeded %d days of history", days or config.SEED_DAYS)


def add_keyword(session: Session, term: str, backfill: bool = True):
    """Add a keyword and (in mock mode) backfill its history + alerts.

    Returns the Keyword (existing or new), or None for an empty term.
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
        seed_keyword_history(session, kw)
    return kw


def remove_keyword(session: Session, keyword_id: int) -> bool:
    kw = session.get(Keyword, keyword_id)
    if not kw:
        return False
    session.query(AlertEvent).filter_by(keyword_id=keyword_id).delete()
    session.delete(kw)  # BuzzDaily rows cascade
    session.commit()
    return True


def maybe_seed(session: Session) -> bool:
    """Seed defaults + history on an empty DB. Returns True if seeding ran."""
    if session.query(Keyword).first() is None:
        ensure_default_keywords(session)
    if session.query(BuzzDaily).first() is None:
        seed_history(session)
        return True
    return False
