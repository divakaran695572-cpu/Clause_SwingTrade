"""Web server: serves the phone app + JSON API, runs the screen, schedules runs."""
import hashlib
import hmac
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db
from .screener import run_screen

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
COOKIE = "screener_auth"

# ---------- running a screen (one at a time) ----------

_run_lock = threading.Lock()
_current = {"id": None, "trigger": None, "started": None}


def _do_run(run_id: int, trigger: str):
    try:
        result, raw, usage = run_screen(trigger)
        db.finish_run(run_id, "done", result=result, raw_text=raw, usage=usage)
    except Exception as e:  # noqa: BLE001 - we want to store any failure
        traceback.print_exc()
        db.finish_run(run_id, "error", error=f"{type(e).__name__}: {e}"[:2000])
    finally:
        _current.update(id=None, trigger=None, started=None)
        _run_lock.release()


def start_run(trigger: str):
    """Start a run in the background. Returns run id, or None if one is already running."""
    if not _run_lock.acquire(blocking=False):
        return None
    run_id = db.create_run(trigger)
    _current.update(id=run_id, trigger=trigger, started=time.time())
    threading.Thread(target=_do_run, args=(run_id, trigger), daemon=True).start()
    return run_id


# ---------- scheduler ----------

scheduler = BackgroundScheduler()


def _hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def _scheduled(trigger: str):
    if start_run(trigger) is None:
        print(f"[scheduler] {trigger}: skipped, a run is already in progress")


def setup_schedule():
    if not config.SCHEDULE_ENABLED:
        return
    h, m = _hm(config.EU_RUN_TIME)
    scheduler.add_job(
        _scheduled, CronTrigger(day_of_week="mon-fri", hour=h, minute=m, timezone=config.EU_RUN_TZ),
        args=["eu_open"], id="eu_open", misfire_grace_time=3600, coalesce=True, replace_existing=True,
    )
    h, m = _hm(config.US_RUN_TIME)
    scheduler.add_job(
        _scheduled, CronTrigger(day_of_week="mon-fri", hour=h, minute=m, timezone=config.US_RUN_TZ),
        args=["us_close"], id="us_close", misfire_grace_time=3600, coalesce=True, replace_existing=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.mark_stale_runs_failed()
    setup_schedule()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Swing Screener", lifespan=lifespan)

# ---------- auth (single shared password, signed cookie) ----------


def _token() -> str:
    return hmac.new(config.SESSION_SECRET.encode(), b"swing-screener-auth-v1", hashlib.sha256).hexdigest()


def require_auth(request: Request):
    if not config.APP_PASSWORD:
        raise HTTPException(503, "APP_PASSWORD is not set on the server")
    cookie = request.cookies.get(COOKIE, "")
    if not hmac.compare_digest(cookie, _token()):
        raise HTTPException(401, "Not logged in")


_attempts: dict[str, list[float]] = {}


def _check_rate_limit(ip: str):
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < 600]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many attempts, try again in 10 minutes")
    recent.append(now)
    _attempts[ip] = recent


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    if not config.APP_PASSWORD:
        raise HTTPException(503, "APP_PASSWORD is not set on the server")
    _check_rate_limit(request.client.host if request.client else "unknown")
    if not hmac.compare_digest(body.password.encode(), config.APP_PASSWORD.encode()):
        raise HTTPException(401, "Wrong password")
    response.set_cookie(
        COOKIE, _token(), max_age=60 * 60 * 24 * 90, httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------- API ----------


@app.get("/api/me", dependencies=[Depends(require_auth)])
def me():
    return {"ok": True}


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status():
    nxt = []
    for job in scheduler.get_jobs():
        if job.next_run_time:
            nxt.append({"name": job.id, "at": job.next_run_time.isoformat()})
    nxt.sort(key=lambda x: x["at"])
    return {
        "running": _current["id"] is not None,
        "current": dict(_current) if _current["id"] else None,
        "next_runs": nxt,
        "schedule": {
            "eu_open": f"{config.EU_RUN_TIME} {config.EU_RUN_TZ}",
            "us_close": f"{config.US_RUN_TIME} {config.US_RUN_TZ}",
            "enabled": config.SCHEDULE_ENABLED,
        },
        "model": config.MODEL,
        "danelfin": bool(config.DANELFIN_API_KEY),
        "mock": config.MOCK_MODE,
        "manual_runs_today": db.count_manual_today(),
        "manual_runs_limit": config.MAX_MANUAL_RUNS_PER_DAY,
    }


@app.get("/api/latest", dependencies=[Depends(require_auth)])
def latest():
    return db.latest_done() or {}


@app.get("/api/runs", dependencies=[Depends(require_auth)])
def runs(limit: int = 30):
    return db.list_runs(max(1, min(limit, 100)))


@app.get("/api/runs/{run_id}", dependencies=[Depends(require_auth)])
def run_detail(run_id: int):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@app.post("/api/run", dependencies=[Depends(require_auth)])
def run_now():
    if db.count_manual_today() >= config.MAX_MANUAL_RUNS_PER_DAY:
        raise HTTPException(429, f"Daily manual run limit reached ({config.MAX_MANUAL_RUNS_PER_DAY})")
    run_id = start_run("manual")
    if run_id is None:
        raise HTTPException(409, "A run is already in progress")
    return {"run_id": run_id}


@app.get("/healthz")
def healthz():
    return {"ok": True}


# The phone app itself (must be mounted last).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
