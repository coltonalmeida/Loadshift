"""Render Cron Job entrypoint: rebuild the forecast, publish it to Key Value.

This is the ONLY process that loads LightGBM or touches IESO. The web service
reads what this writes and nothing else, which is the rule in CLAUDE.md
("Never fetch IESO or run the model on a request path") enforced by topology
rather than by convention.

Runs hourly as `loadshift-refresh`. A failed run leaves the previous payload in
Key Value untouched and exits non-zero so Render marks the run failed and can
notify — the site keeps serving last-known-good with stale=true either way.
"""
from __future__ import annotations

import os
import sys
import time

from . import cache, kv

ATTEMPTS = 3
# Open-Meteo 429s on Render's shared egress IP are transient bursts, not an
# exhausted quota; a short backoff clears them well inside the hourly budget.
BACKOFF_S = 20


def _render_env() -> dict:
    return {
        "service": os.environ.get("RENDER_SERVICE_NAME"),
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or None,
        "branch": os.environ.get("RENDER_GIT_BRANCH"),
        "instance": os.environ.get("RENDER_INSTANCE_ID"),
        "is_preview": os.environ.get("IS_PULL_REQUEST") == "true",
    }


def run() -> bool:
    started = time.time()
    ok = False
    for i in range(ATTEMPTS):
        ok = cache.refresh()
        if ok:
            break
        if i < ATTEMPTS - 1:
            wait = BACKOFF_S * (2 ** i)
            print(f"[refresh_job] attempt {i + 1}/{ATTEMPTS} failed, retrying in {wait}s")
            time.sleep(wait)

    payload = cache.get() if ok else None
    meta = {
        "ok": ok,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "duration_s": round(time.time() - started, 1),
        "attempts": ATTEMPTS if not ok else i + 1,
        "generated_at": payload.get("generated_at") if payload else None,
        "weather_source": payload.get("weather_source") if payload else None,
        "error": cache.diagnostics()["last_error"],
        **_render_env(),
    }
    # Written whether or not the rebuild worked: a run that failed is exactly
    # what an operator needs to see on /api/platform, and the previous forecast
    # is still in FORECAST_KEY untouched.
    if not kv.set_json(kv.FORECAST_META_KEY, meta) and kv.url():
        print("[refresh_job] warning: could not write run metadata to Key Value")
    print(f"[refresh_job] {'ok' if ok else 'FAILED'} in {meta['duration_s']}s")
    return ok


def main() -> int:
    if not kv.url():
        # Not fatal locally, but on Render it means the Blueprint wiring broke
        # and the payload would die with this container.
        print("[refresh_job] KV_URL unset - forecast will not outlive this process")
    return 0 if run() else 1


if __name__ == "__main__":
    sys.exit(main())
