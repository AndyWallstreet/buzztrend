"""Read-side aggregation queries for the dashboard/API."""
from datetime import date as date_cls, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..models import AlertEvent, BuzzDaily, Keyword


def _date_range(days: int):
    today = date_cls.today()
    start = today - timedelta(days=days - 1)
    return [start + timedelta(days=i) for i in range(days)]


def keyword_overview(session: Session, days: int = 30):
    """Per-keyword totals + a daily total sparkline for the last `days`."""
    dates = _date_range(days)
    start = dates[0]
    out = []
    for kw in session.query(Keyword).order_by(Keyword.term).all():
        rows = (session.query(BuzzDaily.date, func.sum(BuzzDaily.count))
                .filter(BuzzDaily.keyword_id == kw.id, BuzzDaily.date >= start)
                .group_by(BuzzDaily.date).all())
        by_date = {d: int(c) for d, c in rows}
        spark = [by_date.get(d, 0) for d in dates]
        total = sum(spark)
        prev = spark[-2] if len(spark) > 1 else 0
        last = spark[-1] if spark else 0
        change = ((last - prev) / prev * 100) if prev else 0.0
        out.append({
            "id": kw.id, "term": kw.term, "active": kw.active,
            "total": total, "today": last, "change_pct": round(change, 1),
            "spark": spark,
        })
    out.sort(key=lambda k: k["total"], reverse=True)
    return out


def timeseries(session: Session, keyword_id: int, days: int = 30):
    """{ dates: [...], series: { channel: [...] }, totals: [...] }."""
    dates = _date_range(days)
    start = dates[0]
    labels = [d.isoformat() for d in dates]

    rows = (session.query(BuzzDaily.channel, BuzzDaily.date, BuzzDaily.count)
            .filter(BuzzDaily.keyword_id == keyword_id, BuzzDaily.date >= start)
            .all())
    grid = {ch: {} for ch in config.CHANNEL_KEYS}
    for ch, d, c in rows:
        grid.setdefault(ch, {})[d] = c

    series = {}
    for ch in config.CHANNEL_KEYS:
        series[ch] = [int(grid.get(ch, {}).get(d, 0)) for d in dates]
    totals = [sum(series[ch][i] for ch in config.CHANNEL_KEYS)
              for i in range(len(dates))]
    return {"dates": labels, "series": series, "totals": totals}


def breakdown(session: Session, keyword_id: int, days: int = 30):
    """Total buzz per channel over the window."""
    start = date_cls.today() - timedelta(days=days - 1)
    rows = (session.query(BuzzDaily.channel, func.sum(BuzzDaily.count))
            .filter(BuzzDaily.keyword_id == keyword_id, BuzzDaily.date >= start)
            .group_by(BuzzDaily.channel).all())
    got = {ch: int(c) for ch, c in rows}
    return [{"channel": ch, "total": got.get(ch, 0)} for ch in config.CHANNEL_KEYS]


def recent_alerts(session: Session, limit: int = 50):
    rows = (session.query(AlertEvent)
            .order_by(AlertEvent.date.desc(), AlertEvent.id.desc())
            .limit(limit).all())
    return [{
        "id": a.id, "keyword_id": a.keyword_id,
        "term": a.keyword.term if a.keyword else "?",
        "channel": a.channel,
        "channel_label": config.CHANNELS_BY_KEY.get(a.channel, {}).get("label", a.channel),
        "date": a.date.isoformat(), "count": a.count,
        "baseline": a.baseline, "ratio": a.ratio, "message": a.message,
    } for a in rows]
