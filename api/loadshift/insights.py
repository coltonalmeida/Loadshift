"""Gemini-generated insights over computed Green Button stats.

Grounded generation only: the model receives our computed stats JSON and is
told to reason from those numbers, nothing else. Any failure (no key, quota,
timeout, malformed reply) returns None and the UI simply omits the card.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque

import requests

MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
TIMEOUT_S = 12

# Light global rate limit so a demo page can't burn the free tier.
_calls: deque[float] = deque(maxlen=30)


def _allowed() -> bool:
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= 20:
        return False
    _calls.append(now)
    return True


def _generate(prompt: str, json_mode: bool) -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not _allowed():
        return None
    body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"response_mime_type": "application/json"}
    try:
        r = requests.post(URL, params={"key": key}, json=body, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # noqa: BLE001 - degrade to no card, never an error
        print(f"[insights] generation failed: {type(e).__name__}: {e}")
        return None


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


def report(stats: dict) -> dict | None:
    """Personalized report from analysis stats, or None."""
    slim = {k: v for k, v in stats.items() if k not in ("monthly", "usage_by_hour")}
    slim["usage_by_hour_kwh"] = stats.get("usage_by_hour")
    text = _generate(REPORT_PROMPT.format(stats=json.dumps(slim)), json_mode=True)
    if not text:
        return None
    try:
        parsed = json.loads(text)
        recs = list(parsed["recommendations"])[:3]
        return {"summary": str(parsed["summary"]), "recommendations": recs, "model": MODEL}
    except Exception:  # noqa: BLE001
        return None


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


def ask(question: str, stats: dict) -> str | None:
    slim = {k: v for k, v in stats.items() if k != "monthly"}
    return _generate(
        ASK_PROMPT.format(stats=json.dumps(slim), question=question[:300]),
        json_mode=False,
    )
