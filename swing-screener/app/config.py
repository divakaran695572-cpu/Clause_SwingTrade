"""All settings come from environment variables (see .env.example)."""
import os
import secrets
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DANELFIN_API_KEY = os.getenv("DANELFIN_API_KEY", "")
DANELFIN_URL = os.getenv("DANELFIN_URL", "https://mcp.danelfin.com/mcp")

# Model used for the screen. Change it in Render's environment settings any time.
MODEL = os.getenv("MODEL", "claude-sonnet-5")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "32000"))
MAX_WEB_SEARCHES = int(os.getenv("MAX_WEB_SEARCHES", "30"))
# Web search tool version. Newer versions exist (e.g. web_search_20260318); change here if needed.
WEB_SEARCH_TOOL = os.getenv("WEB_SEARCH_TOOL", "web_search_20250305")
MAX_DANELFIN_CALLS = int(os.getenv("MAX_DANELFIN_CALLS", "10"))

# Login for the app (it spends your API money, so it must be private).
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)

# Where the database lives. On Render this should be the persistent disk (/var/data).
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "screener.db"

# Scheduled runs (weekdays). Times are LOCAL to the given time zone, so daylight
# saving changes in Europe and the US are handled automatically.
SCHEDULE_ENABLED = _bool("SCHEDULE_ENABLED", True)
EU_RUN_TIME = os.getenv("EU_RUN_TIME", "09:05")      # Xetra opens 09:00 Berlin
EU_RUN_TZ = os.getenv("EU_RUN_TZ", "Europe/Berlin")
US_RUN_TIME = os.getenv("US_RUN_TIME", "16:10")      # NYSE closes 16:00 New York
US_RUN_TZ = os.getenv("US_RUN_TZ", "America/New_York")

# Safety limit so a stuck button or a bug cannot burn through your API budget.
MAX_MANUAL_RUNS_PER_DAY = int(os.getenv("MAX_MANUAL_RUNS_PER_DAY", "6"))

# MOCK_MODE=true returns sample data and makes no API calls (for testing the app).
MOCK_MODE = _bool("MOCK_MODE", False)
