"""FastAPI app: HTML dashboard + JSON API."""
import logging
from datetime import date as date_cls
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import config
from .database import get_session, init_db, session_scope
from .models import Keyword
from .scheduler import start_scheduler
from .services import analytics
from .services.alerts import check_alerts
from .services.collection import collect_for_day
from .services.seed import maybe_seed

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="BuzzTrend")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def _startup():
    init_db()
    with session_scope() as session:
        seeded = maybe_seed(session)
    if seeded:
        logging.getLogger("buzztrend").info("seeded demo data on first run")
    start_scheduler()


# ------------------------- HTML pages -------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "channels": config.CHANNELS, "use_mock": config.USE_MOCK,
    })


@app.get("/keyword/{keyword_id}", response_class=HTMLResponse)
def keyword_page(request: Request, keyword_id: int,
                 session: Session = Depends(get_session)):
    kw = session.get(Keyword, keyword_id)
    if not kw:
        raise HTTPException(404, "keyword not found")
    return templates.TemplateResponse(request, "keyword.html", {
        "keyword": kw, "channels": config.CHANNELS,
    })


@app.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request):
    return templates.TemplateResponse(request, "alerts.html", {})


# ------------------------- JSON API -------------------------

@app.get("/api/overview")
def api_overview(days: int = 30, session: Session = Depends(get_session)):
    return {"days": days, "keywords": analytics.keyword_overview(session, days)}


@app.get("/api/keyword/{keyword_id}/timeseries")
def api_timeseries(keyword_id: int, days: int = 30,
                   session: Session = Depends(get_session)):
    return analytics.timeseries(session, keyword_id, days)


@app.get("/api/keyword/{keyword_id}/breakdown")
def api_breakdown(keyword_id: int, days: int = 30,
                  session: Session = Depends(get_session)):
    return {"breakdown": analytics.breakdown(session, keyword_id, days)}


@app.get("/api/alerts")
def api_alerts(limit: int = 50, session: Session = Depends(get_session)):
    return {"alerts": analytics.recent_alerts(session, limit)}


@app.get("/api/channels")
def api_channels():
    return {"channels": config.CHANNELS}


@app.post("/api/keywords")
def api_add_keyword(term: str = Form(...),
                    session: Session = Depends(get_session)):
    term = term.strip()
    if not term:
        raise HTTPException(400, "empty term")
    existing = session.query(Keyword).filter_by(term=term).first()
    if existing:
        return {"id": existing.id, "term": existing.term, "created": False}
    kw = Keyword(term=term)
    session.add(kw)
    session.commit()
    # Backfill so the new keyword shows history immediately (mock mode).
    if config.USE_MOCK:
        from .collectors import mock_collectors
        from datetime import timedelta
        cols = mock_collectors()
        today = date_cls.today()
        for offset in range(config.SEED_DAYS, -1, -1):
            collect_for_day(session, today - timedelta(days=offset), cols)
        for offset in range(config.SEED_DAYS, -1, -1):
            check_alerts(session, today - timedelta(days=offset))
    return {"id": kw.id, "term": kw.term, "created": True}


@app.delete("/api/keywords/{keyword_id}")
def api_delete_keyword(keyword_id: int, session: Session = Depends(get_session)):
    kw = session.get(Keyword, keyword_id)
    if not kw:
        raise HTTPException(404, "not found")
    session.delete(kw)
    session.commit()
    return {"deleted": keyword_id}


@app.post("/api/collect")
def api_collect_now(session: Session = Depends(get_session)):
    written = collect_for_day(session, date_cls.today())
    alerts = check_alerts(session, date_cls.today())
    return {"points": written, "new_alerts": alerts}
