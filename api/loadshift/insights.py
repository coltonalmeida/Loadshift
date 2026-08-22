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
from collections import OrderedDict

import requests

from . import kv

MODEL = "gemini-3.5-flash-lite"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
# Calls land in ~1.4s; a longer wait is a dead call holding a worker, not a slow one.
TIMEOUT_S = 12

# The report is a <=90-word summary plus three one-sentence recommendations, and
# an answer is <=110 words. Nothing legitimate approaches this. It is a stop on
# runaway generation — the main way one of these calls goes slow — not a target.
# Do not lower it far: a truncated reply fails JSON parsing as "malformed".
MAX_OUTPUT_TOKENS = 512

# Identical stats reuse a report. The bundled sample is byte-identical on every
# load, so only the first visitor pays the latency and the quota.
#
# Two tiers: this per-process LRU, and Render Key Value behind it. The LRU alone
# is emptied by every deploy and is not shared between instances, so the sample
# report — the one a judge is most likely to trigger — was being regenerated
# and re-billed far more often than "identical stats reuse a report" implies.
_CACHE_MAX = 32
_cache: OrderedDict[str, dict] = OrderedDict()
_KV_TTL_S = 24 * 3600

# Google issues keys in more than one shape (AIza..., AQ....); cover both.
_KEY_RE = re.compile(r"(?:AIza|AQ\.)[0-9A-Za-z_\-.]{10,}")


def available() -> bool:
    """Is a shared key configured? The UI asks for one only when this is False."""
    return bool(os.environ.get("GEMINI_API_KEY"))


class InsightsError(Exception):
    """Why generation failed, so the caller can answer honestly.

    reason: no_key | quota | upstream | malformed
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _scrub(msg: str) -> str:
    """Never let a key reach the log, whatever an exception carries."""
    return _KEY_RE.sub("<key>", msg)


def _generate(prompt: str, json_mode: bool, user_key: str | None = None) -> str:
    key = user_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise InsightsError("no_key")
    # No thinkingConfig on purpose. This model defaults to no thinking (measured
    # 0 thought tokens, ~1.4s); an explicit thinkingBudget of 0 is rejected 400,
    # and the old gemini-3.6-flash ignored a budget of 128 and spent 674 thought
    # tokens over 15s. Do not reinstate it without re-measuring.
    body: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    if json_mode:
        body["generationConfig"]["response_mime_type"] = "application/json"
    try:
        # Header, not a query param: requests builds HTTPError messages from the
        # full URL, which would print the key straight into the server log.
        r = requests.post(
            URL, headers={"x-goog-api-key": key}, json=body, timeout=TIMEOUT_S
        )
        if r.status_code == 429:
            raise InsightsError("quota")
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except InsightsError:
        raise
    except Exception as e:  # noqa: BLE001 - degrade to no card, never an error
        print(f"[insights] generation failed: {type(e).__name__}: {_scrub(str(e))}")
        raise InsightsError("upstream") from e


def _canon(v):
    """Normalise numbers so the same statistics always hash the same way.

    These stats reach us two ways: echoed back by the browser, and computed
    server-side when the cron pre-warms the sample report. Python writes an
    integral float as `7036.0` and JavaScript writes it as `7036`, so the two
    paths would otherwise produce different JSON for identical numbers and miss
    each other's cache entry. Collapsing integral floats to int makes the digest
    independent of who serialised it.
    """
    if isinstance(v, bool):  # bool is an int subclass; must be checked first
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 6)
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    return v


def _slim(stats: dict) -> dict:
    """Only what the prompts reason over: drops the bulky month/day series and
    any report the client echoed back at us."""
    drop = {"ai_report", "ai_available", "monthly", "worst_days", "usage_by_hour"}
    slim = {k: v for k, v in stats.items() if k not in drop}
    if stats.get("usage_by_hour") is not None:
        slim["usage_by_hour_kwh"] = stats["usage_by_hour"]
    return _canon(slim)


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
- Write money as $1,234.56 and shares as 12.3%. Never spell either out.
- No exclamation marks. No em dashes.

Household stats JSON:
{stats}
"""


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _cached(key: str):
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    # L2: written by whichever instance generated it, survives redeploys.
    blob = kv.get_json(kv.insight_key(key))
    if blob is None:
        return None
    value = blob.get("v")
    if value is not None:
        _remember(key, value)
    return value


def _remember(key: str, value):
    _cache[key] = value
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return value


def _store(key: str, value):
    kv.set_json(kv.insight_key(key), {"v": value}, ttl_s=_KV_TTL_S)
    return _remember(key, value)


def report_key(stats: dict) -> str:
    """Cache key for a report, so callers can test for a hit without paying."""
    return _digest("report", json.dumps(_slim(stats), sort_keys=True, default=str))


def cached_report(stats: dict) -> dict | None:
    return _cached(report_key(stats))


def report(stats: dict, user_key: str | None = None) -> dict:
    """Personalized report from analysis stats. Raises InsightsError."""
    slim = _slim(stats)
    digest = report_key(stats)
    hit = _cached(digest)
    if hit is not None:
        return hit

    text = _generate(REPORT_PROMPT.format(stats=_dumps(slim)), json_mode=True,
                     user_key=user_key)
    try:
        parsed = json.loads(text)
        out = {
            "summary": str(parsed["summary"]),
            "recommendations": [str(r) for r in list(parsed["recommendations"])[:3]],
            "model": MODEL,
        }
    except Exception as e:  # noqa: BLE001
        raise InsightsError("malformed") from e

    return _store(digest, out)


ASK_PROMPT = """You are the analysis layer of Loadshift, a tool that helps
Ontario households shift electricity use to low-emission, low-price hours.
Answer the user's question about their own electricity data.

Rules:
- Ground every claim in the stats JSON below; if the stats cannot answer it,
  say so briefly and suggest what could.
- At most 110 words. Plain language, second person. No exclamation marks.
  No em dashes.
- Write money as $1,234.56 and shares as 12.3%. Never spell either out.
- Context you may use: Ontario time-of-use rates are 9.8/15.7/20.3 cents per
  kWh; the Ultra-Low Overnight plan is 3.9 cents from 11 PM to 7 AM but 39.1
  cents on weekdays 4 PM to 9 PM. Marginal grid emissions in Ontario are
  usually set by natural gas plants and peak in the evening.

Household stats JSON:
{stats}

Question: {question}
"""


def ask_key(question: str, stats: dict) -> str:
    return _digest(
        "ask",
        question[:300],
        json.dumps(_slim(stats), sort_keys=True, default=str),
    )


def cached_ask(question: str, stats: dict) -> str | None:
    return _cached(ask_key(question, stats))


def ask(question: str, stats: dict, user_key: str | None = None) -> str:
    """Answer a follow-up. Raises InsightsError. Repeat questions are free."""
    digest = ask_key(question, stats)
    hit = _cached(digest)
    if hit is not None:
        return hit
    answer = _generate(
        ASK_PROMPT.format(stats=_dumps(_slim(stats)), question=question[:300]),
        json_mode=False,
        user_key=user_key,
    )
    return _store(digest, answer.strip())
