"""Background scheduler that collects + checks alerts on an interval."""
from __future__ import annotations

import logging
from datetime import date as date_cls

from apscheduler.schedulers.background import BackgroundScheduler

from . import config
from .database import session_scope
from .services.alerts import check_alerts
from .services.collection import collect_for_day

log = logging.getLogger("buzztrend.scheduler")
_scheduler: BackgroundScheduler | None = None


def run_collection_job() -> None:
    with session_scope() as session:
        collect_for_day(session, date_cls.today())
        check_alerts(session, date_cls.today())


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(run_collection_job, "interval",
                  minutes=config.COLLECT_INTERVAL_MINUTES,
                  id="collect", replace_existing=True)
    sched.start()
    log.info("scheduler started (every %d min)", config.COLLECT_INTERVAL_MINUTES)
    _scheduler = sched
    return sched
