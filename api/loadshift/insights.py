"""Gemini-generated insights over computed Green Button stats.

Grounded generation only: the model receives our computed stats JSON and is
told to reason from those numbers, nothing else. Any failure (no key, quota,
timeout, malformed reply) returns None and the UI simply omits the card.

The shared key lives only in the server environment and never reaches the
browser. A caller may pass their own key per request; it is used for that one
call and is never logged, cached, or stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import OrderedDict, deque

import requests

MODEL = "gemini-3.6-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
TIMEOUT_S = 25

# Light global rate limit so a demo page can't burn the shared free tier.
_calls: deque[float] = deque(maxlen=30)

# Identical stats reuse a report. The bundled sample is byte-identical on every
# load, so only the first visitor pays the latency and the quota.
_CACHE_MAX = 32
_cache: OrderedDict[str, dict] = OrderedDict()

# Google issues keys in more than one shape (AIza..., AQ....); cover both.
_KEY_RE = re.compile(r"(?:AIza|AQ\.)[0-9A-Za-z_\-.]{10,}")


def available() -> bool:
    """Is a shared key configured? The UI asks for one only when this is False."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def _allowed() -> bool:
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= 20:
        return False
    _calls.append(now)
    return True


def _scrub(msg: str) -> str:
    """Never let a key reach the log, whatever an exception carries."""
    return _KEY_RE.sub("<key>", msg)


def _generate(prompt: str, json_mode: bool, user_key: str | None = None) -> str | None:
    key = user_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    # Someone spending their own key is not competing for our shared quota.
    if not user_key and not _allowed():
        return None
    body: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        # low thinking budget: these are small grounded summaries, speed matters
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 128}},
    }
    if json_mode:
        body["generationConfig"]["response_mime_type"] = "application/json"
    try:
        # Header, not a query param: requests builds HTTPError messages from the
        # full URL, which would print the key straight into the server log.
        r = requests.post(
            URL, headers={"x-goog-api-key": key}, json=body, timeout=TIMEOUT_S
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # noqa: BLE001 - degrade to no card, never an error
        print(f"[insights] generation failed: {type(e).__name__}: {_scrub(str(e))}")
        return None


def _slim(stats: dict) -> dict:
    """Only what the prompts reason over: drops the bulky month/day series and
    any report the client echoed back at us."""
    drop = {"ai_report", "ai_available", "monthly", "worst_days", "usage_by_hour"}
    slim = {k: v for k, v in stats.items() if k not in drop}
    if stats.get("usage_by_hour") is not None:
        slim["usage_by_hour_kwh"] = stats["usage_by_hour"]
    return slim


def _dumps(obj: dict) -> str:
    return json.dumps(obj, default=str)


REPORT_PROMPT = """You are the analysis layer of Loadshift, a tool that helps
Ontario households shift electricity use to hours when the marginal grid
emissions and prices are low. Below are computed statistics from one
household's smart-meter year. Write for that household.

Rules:
- Use ONLY the numbers given. Do not invent data.
- Return JSON: {{"summary": string, "recommendations": [string, string, string]}}
- summary: at most 90 words, plain language, second person, specific to their
  numbers (mention their timing score, evening share, and dollar figures).
- recommendations: exactly 3, each one sentence, concrete and actionable for
  this household (appliance timing, rate-plan choice, habits). If cost_ulo is
  well below cost_tou, one recommendation should mention the Ultra-Low
  Overnight plan.
- No exclamation marks. No em dashes.

Household stats JSON:
{stats}
"""


def report(stats: dict, user_key: str | None = None) -> dict | None:
    """Personalized report from analysis stats, or None."""
    slim = _slim(stats)
    digest = hashlib.sha256(
        json.dumps(slim, sort_keys=True, default=str).encode()
    ).hexdigest()
    hit = _cache.get(digest)
    if hit is not None:
        _cache.move_to_end(digest)
        return hit

    text = _generate(REPORT_PROMPT.format(stats=_dumps(slim)), json_mode=True,
                     user_key=user_key)
    if not text:
        return None
    try:
        parsed = json.loads(text)
        out = {
            "summary": str(parsed["summary"]),
            "recommendations": [str(r) for r in list(parsed["recommendations"])[:3]],
            "model": MODEL,
        }
    except Exception:  # noqa: BLE001
        return None

    _cache[digest] = out
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return out


ASK_PROMPT = """You are the analysis layer of Loadshift, a tool that helps
Ontario households shift electricity use to low-emission, low-price hours.
Answer the user's question about their own electricity data.

Rules:
- Ground every claim in the stats JSON below; if the stats cannot answer it,
  say so briefly and suggest what could.
- At most 110 words. Plain language, second person. No exclamation marks.
  No em dashes.
- Context you may use: Ontario time-of-use rates are 9.8/15.7/20.3 cents per
  kWh; the Ultra-Low Overnight plan is 3.9 cents from 11 PM to 7 AM but 39.1
  cents on weekdays 4 PM to 9 PM. Marginal grid emissions in Ontario are
  usually set by natural gas plants and peak in the evening.

Household stats JSON:
{stats}

Question: {question}
"""


def ask(question: str, stats: dict, user_key: str | None = None) -> str | None:
    return _generate(
        ASK_PROMPT.format(stats=_dumps(_slim(stats)), question=question[:300]),
        json_mode=False,
        user_key=user_key,
    )
