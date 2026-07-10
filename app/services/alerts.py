"""Spike detection: today's count vs the trailing 7-day average."""
from __future__ import annotations

import logging
from datetime import date as date_cls, timedelta

from sqlalchemy.orm import Session

from .. import config
from ..models import AlertEvent, BuzzDaily, Keyword

log = logging.getLogger("buzztrend.alerts")


def _count(session: Session, keyword_id: int, channel: str, day: date_cls):
    row = (session.query(BuzzDaily)
           .filter_by(keyword_id=keyword_id, channel=channel, date=day)
           .one_or_none())
    return row.count if row else None


def check_alerts(session: Session, day: date_cls | None = None) -> int:
    """Create AlertEvents for spikes on `day`. Returns number of new alerts."""
    day = day or date_cls.today()
    ratio_threshold = config.ALERT_SPIKE_RATIO
    new_alerts = 0

    for kw in session.query(Keyword).filter_by(active=True).all():
        for channel in config.CHANNEL_KEYS:
            today = _count(session, kw.id, channel, day)
            if not today:
                continue

            window = [
                c for c in (
                    _count(session, kw.id, channel, day - timedelta(days=d))
                    for d in range(1, 8)
                ) if c is not None
            ]
            if len(window) < 3:  # not enough history to judge
                continue
            baseline = sum(window) / len(window)
            if baseline <= 0:
                continue

            ratio = today / baseline
            if ratio < ratio_threshold:
                continue

            exists = (session.query(AlertEvent)
                      .filter_by(keyword_id=kw.id, channel=channel, date=day)
                      .first())
            if exists:
                continue

            label = config.CHANNELS_BY_KEY[channel]["label"]
            session.add(AlertEvent(
                keyword_id=kw.id, channel=channel, date=day, count=today,
                baseline=round(baseline, 1), ratio=round(ratio, 2),
                message=(f"'{kw.term}' buzz on {label} is {ratio:.1f}× its "
                         f"7-day average ({today} vs ~{baseline:.0f})."),
            ))
            new_alerts += 1

    session.commit()
    if new_alerts:
        log.info("created %d alert(s) for %s", new_alerts, day)
    return new_alerts
