# Deploying Loadshift on Render

Loadshift runs as four Render resources declared in a single Blueprint
([`render.yaml`](render.yaml)). One `git push` deploys the whole product.

```
                  ┌─────────────────────────────┐
  browser ───────▶│ loadshift-web       (web)   │  Next.js 16 · public URL
                  │  /api/* proxied, same-origin│
                  └──────────────┬──────────────┘
                                 │  Render private network
                                 │  http://loadshift-api:10000
                  ┌──────────────▼──────────────┐
                  │ loadshift-api       (web)   │  FastAPI · reads cache only
                  └──────────────┬──────────────┘
                                 │  KV_URL (internal)
                  ┌──────────────▼──────────────┐
                  │ loadshift-cache  (keyvalue) │  Valkey 8 · survives deploys
                  └──────────────▲──────────────┘
                                 │  publishes forecast + run metadata
                  ┌──────────────┴──────────────┐
                  │ loadshift-refresh   (cron)  │  hourly · the only model run
                  └─────────────────────────────┘
```

## Why it is split this way

Render containers have an **ephemeral filesystem**: everything written to disk
is destroyed on the next deploy. Loadshift used to keep four things in that
container, and ordinary deploys kept wiping them.

| Problem | Fix |
|---|---|
| Forecast cache lived in `api/data/`. A fresh instance had nothing and returned 503 until a background thread rebuilt it. | Forecast is published to **Key Value** by the cron job. A redeployed instance is warm on its first request. |
| Weather last-known-good lived in the same directory, so a cold boot that hit an Open-Meteo rate limit fell all the way back to a committed seed snapshot. | Last-good weather is in **Key Value**, so a cold instance still has recent real weather. |
| The shared Gemini key budget was an in-process counter: every deploy handed every visitor a fresh allowance, and the 300/day global cap multiplied by the instance count. | Counters are **Key Value sorted sets**, shared across instances and surviving restarts. |
| The generated-insight cache was per-process, so the bundled sample report was regenerated — and re-billed — on every restart and by every instance. | Cached in **Key Value** for 24h, keyed by a hash of the statistics. |
| APScheduler ran LightGBM **inside the web service**, so a request-serving process carried a ~150 MB model dependency, and two instances would have run two schedulers. | The model runs only in the **cron job**. The web service no longer imports LightGBM at all. |

That last one is a project rule, from `CLAUDE.md`: *never fetch IESO or run the
model on a request path.* It is now enforced by topology rather than by
convention — the web service cannot run the model, because it never loads it.

## The resources

| Resource | Type | Notes |
|---|---|---|
| `loadshift-web` | `web` (Node) | Next.js. Proxies `/api/*` to the API over the private network. |
| `loadshift-api` | `web` (Python) | FastAPI. Health check at `/api/health`. Reads the cache; never writes it. |
| `loadshift-refresh` | `cron` | `7 * * * *`. Runs `python -m loadshift.refresh_job`. |
| `loadshift-cache` | `keyvalue` | Valkey 8. `noeviction` — the forecast must never be evicted. Internal-only (`ipAllowList: []`). |

Both Python services share an environment group (`loadshift-shared`) carrying
`GEMINI_API_KEY` and a pinned `PYTHON_VERSION`. `KV_URL` is wired by
`fromService`, so no connection string is ever copied by hand.

### Same-origin API, over the private network

The browser only ever calls `loadshift-web`'s own origin. `/api/*` is proxied by
[`web/app/api/[...path]/route.ts`](web/app/api/[...path]/route.ts) to
`loadshift-api`'s **private** hostname. So:

- no CORS preflight on any request,
- API traffic never leaves Render's network,
- no `onrender.com` API URL is baked into the frontend bundle.

It is a route handler rather than a `next.config.ts` rewrite on purpose:
rewrites are evaluated at *build* time and frozen into `routes-manifest.json`,
which would mean the API's hostname had to exist before the frontend could
build, and any change to it would need a rebuild. The route handler reads the
environment per request, so the two services deploy in any order.

## Failure behaviour

The rule is absolute: **never an error page**. Degradation is layered.

| What breaks | What a visitor sees |
|---|---|
| IESO or Open-Meteo is down | The previous forecast, marked `stale: true`, with the time it was built. |
| A cron run fails | Same. The previous forecast stays in Key Value untouched; the footer says the last rebuild failed. |
| Key Value is unreachable | Each service falls back to its old in-process behaviour. `/api/health` reports `cache_backend: "in-process (kv unreachable)"`. |
| A brand-new deploy with no cron run yet | The web service warms the cache once itself, then hands the job back to the cron. |

### Liveness vs readiness

`healthCheckPath` is `/api/health`, which **always** returns 200. That is
deliberate: an instance still waiting on its first forecast is alive, and
failing its health check would make Render roll back a perfectly good deploy.

`/api/ready` is the readiness probe and returns 503 when there is genuinely no
forecast to serve. It is intentionally not wired to `healthCheckPath`.

## First-time setup

1. Push the repo. `render.yaml` must be at the **repo root** to be discovered.
2. Render Dashboard → **New → Blueprint** → select the repo.
3. Supply `GEMINI_API_KEY` when prompted (declared `sync: false`, so it is
   never in git).
4. **Deploy Blueprint.** All four resources are created together.
5. Either wait for the top of the hour or trigger `loadshift-refresh` manually.

Then confirm the architecture is actually doing its job:

```bash
curl https://<api>/api/health     # kv_ok: true, cache_backend: render-key-value
curl https://<api>/api/platform   # refresh.by_service == "loadshift-refresh"
```

`refresh.by_service` is the proof: the forecast being served was built by the
cron job, in a different container, on a different schedule.

**The ship gate** — redeploy `loadshift-api` and immediately request
`/api/forecast`. It should return a warm forecast. Before this architecture,
that same request returned 503 until a background rebuild finished.

## Preview environments

`previews.generation: automatic` clones the entire stack — API, cron job, Key
Value, frontend — for every pull request, expiring after three days. A preview
identifies itself: `IS_PULL_REQUEST` reaches `/api/platform`, and the footer
shows a "preview environment" badge.

## Local development

Nothing here requires Render. `KV_URL` is unset locally, every Key Value call
returns `None`, and the app falls back to the in-process and on-disk paths it
used before.

```bash
# API  (from api/, venv at repo root)
../.venv/Scripts/python -m uvicorn loadshift.main:app --reload --port 8000

# One forecast rebuild, exactly what the cron job runs
../.venv/Scripts/python -m loadshift.refresh_job

# Tests, including the Key-Value-is-down fallback cases
../.venv/Scripts/python -m pytest tests/ -q

# Web (from web/)
npm run dev
```

To exercise the Key Value paths locally, point `KV_URL` at any Redis-compatible
server: `KV_URL=redis://localhost:6379`.
