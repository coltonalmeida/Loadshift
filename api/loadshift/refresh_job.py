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

from . import cache, greenbutton, insights, kv

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


def warm_sample_report() -> str:
    """Generate the bundled sample's AI report once, into Key Value.

    "Try sample data" is the path a visitor with no Green Button file of their
    own takes, and the sample's statistics are byte-identical every time, so its
    report is a constant. Generating it here means that click is instant, costs
    no shared-key quota, and cannot be rate-limited at the worst moment.

    Cheap by construction: only on a cache miss, so at most one call per cache
    lifetime rather than one per hour. Never raises — a failed warm-up must not
    fail the forecast rebuild that is this job's actual purpose.
    """
    if not insights.available():
        return "skipped (no shared key)"
    try:
        kwh = greenbutton.parse(greenbutton.SAMPLE_PATH.read_bytes())
        # Must match what /api/greenbutton/sample returns and the browser echoes
        # back, or the digest differs and this warms nothing. `ai_available` is
        # dropped by _slim(); `sample` is not, so it belongs here.
        stats = {**greenbutton.analyze(kwh), "sample": True}
        if insights.cached_report(stats) is not None:
            return "already cached"
        insights.report(stats)
        return "generated"
    except Exception as e:  # noqa: BLE001 - a warm-up is never worth failing on
        return f"failed: {type(e).__name__}: {e}"[:120]


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

    warm = warm_sample_report()
    print(f"[refresh_job] sample report: {warm}")

    payload = cache.get() if ok else None
    meta = {
        "sample_report": warm,
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
