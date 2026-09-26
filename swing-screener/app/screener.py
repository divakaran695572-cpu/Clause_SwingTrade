"""Runs one swing-trade screen with the Claude API (web search + Danelfin MCP)."""
import json
import re
from datetime import datetime, timezone

from . import config
from .prompt import build_system, build_user

MAX_CONTINUATIONS = 8  # how many times we resume a paused (long) turn


# ---------- parsing ----------

def extract_json(text: str) -> dict:
    """Pull the JSON object out of the model's final answer."""
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = list(reversed(fenced))
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    last_err = None
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError as e:
            last_err = e
    raise ValueError(f"Could not parse JSON from the model answer ({last_err})")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalise(result: dict) -> dict:
    """Light clean-up + sanity checks so the app never breaks on odd values."""
    stocks = result.get("stocks")
    if not isinstance(stocks, list):
        raise ValueError("JSON has no 'stocks' list")
    clean = []
    for i, s in enumerate(stocks[:10], start=1):
        if not isinstance(s, dict):
            continue
        s["rank"] = i
        s["rating"] = s.get("rating") if s.get("rating") in ("green", "yellow", "red") else "yellow"
        # Recompute risk/reward from the worst (highest) entry price so it is consistent.
        entry_top = _num(s.get("entry_high")) or _num(s.get("entry_low"))
        stop, target = _num(s.get("stop")), _num(s.get("target"))
        if entry_top and stop and target and entry_top > stop:
            down = (entry_top - stop) / entry_top * 100
            up = (target - entry_top) / entry_top * 100
            s["downside_pct"] = round(down, 1)
            s["upside_pct"] = round(up, 1)
            s["risk_reward"] = round(up / down, 2) if down > 0 else None
        clean.append(s)
    result["stocks"] = clean
    result.setdefault("as_of", datetime.now(timezone.utc).isoformat(timespec="minutes"))
    result.setdefault("market_note", "")
    return result


# ---------- mock ----------

def _mock(trigger: str) -> tuple[dict, str, dict]:
    sample = {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "market_note": "MOCK DATA - test mode, no real analysis. Two picks share the AI-power theme.",
        "stocks": [
            {
                "rank": 1, "rating": "green", "company": "Sample Bank Corp", "ticker": "SMPL",
                "country": "US", "currency": "USD", "price": 224.0, "today_pct": 0.8,
                "week_pct": 2.1, "month_pct": -6.5, "discount_from_52w_high_pct": -14.0,
                "rsi": 41, "above_50dma": False, "above_200dma": True,
                "why_down": "Sector sell-off on rate fears", "classification": "MOSTLY EXTERNAL",
                "theme": "bond yields", "what_could_improve": "Q3 results, stable rates",
                "timing": "2-4 WEEKS", "fundamental_score": 8, "technical_score": 6,
                "danelfin_ai_score": 8, "danelfin_note": "mock",
                "reversal_evidence": "Held support, higher low", "catalyst": "Q3 earnings",
                "catalyst_date": "2026-10-15", "entry_low": 220, "entry_high": 227,
                "stop": 212, "target": 254, "confidence": 7, "scalable": "Check in Scalable",
                "risks": "Earnings could gap below the stop.",
            },
            {
                "rank": 2, "rating": "yellow", "company": "Example Industrials AG", "ticker": "EXI",
                "country": "Germany", "currency": "EUR", "price": 139.0, "today_pct": -0.4,
                "week_pct": 1.0, "month_pct": -9.0, "discount_from_52w_high_pct": -18.0,
                "rsi": 38, "above_50dma": False, "above_200dma": True,
                "why_down": "AI-power rotation profit-taking", "classification": "EXTERNAL",
                "theme": "AI power rotation", "what_could_improve": "FY results, orders",
                "timing": "4-8 WEEKS", "fundamental_score": 8, "technical_score": 5,
                "danelfin_ai_score": 7, "danelfin_note": "mock",
                "reversal_evidence": "Higher lows", "catalyst": "FY results",
                "catalyst_date": "2026-11-11", "entry_low": 136, "entry_high": 143,
                "stop": 133.5, "target": 162, "confidence": 6, "scalable": "Likely available",
                "risks": "Theme could keep unwinding.",
            },
        ],
    }
    return normalise(sample), "MOCK", {"mock": True}


# ---------- real run ----------

def _final_text(message) -> str:
    return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")


def run_screen(trigger: str) -> tuple[dict, str, dict]:
    """Returns (result_dict, raw_text, usage_dict). Raises on failure."""
    if config.MOCK_MODE:
        return _mock(trigger)
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    import anthropic  # imported here so mock mode works without the package

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=1800.0)

    tools = [
        {
            "type": config.WEB_SEARCH_TOOL,
            "name": "web_search",
            "max_uses": config.MAX_WEB_SEARCHES,
        }
    ]
    mcp_servers = []
    if config.DANELFIN_API_KEY:
        mcp_servers.append(
            {
                "type": "url",
                "url": config.DANELFIN_URL,
                "name": "danelfin",
                "authorization_token": config.DANELFIN_API_KEY,
            }
        )
        tools.append({"type": "mcp_toolset", "mcp_server_name": "danelfin"})

    system = build_system(config.MAX_WEB_SEARCHES, config.MAX_DANELFIN_CALLS)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="minutes")
    messages = [{"role": "user", "content": build_user(trigger, now_iso)}]

    kwargs = dict(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=system,
        tools=tools,
        betas=["mcp-client-2025-11-20"],
    )
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers

    usage = {"input_tokens": 0, "output_tokens": 0, "web_searches": 0, "turns": 0, "model": config.MODEL,
             "danelfin": bool(mcp_servers)}
    final = None
    for _ in range(MAX_CONTINUATIONS + 1):
        with client.beta.messages.stream(messages=messages, **kwargs) as stream:
            final = stream.get_final_message()
        usage["turns"] += 1
        usage["input_tokens"] += getattr(final.usage, "input_tokens", 0) or 0
        usage["output_tokens"] += getattr(final.usage, "output_tokens", 0) or 0
        stu = getattr(final.usage, "server_tool_use", None)
        if stu is not None:
            usage["web_searches"] += getattr(stu, "web_search_requests", 0) or 0
        if final.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": final.content})
            continue
        break

    text = _final_text(final)
    if final.stop_reason == "max_tokens":
        raise RuntimeError("Answer was cut off (max_tokens). Raise MAX_TOKENS or lower MAX_WEB_SEARCHES.")
    result = normalise(extract_json(text))
    return result, text, usage
