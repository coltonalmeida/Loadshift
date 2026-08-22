/**
 * Same-origin proxy onto loadshift-api over Render's private network.
 *
 * Why a route handler and not a next.config rewrite: rewrites are evaluated at
 * BUILD time and baked into routes-manifest.json, so the API's private hostname
 * would have to exist when the frontend builds, and any change to it would need
 * a rebuild to take effect. This reads the env per request instead, so the two
 * services can deploy in any order.
 *
 * The browser therefore only ever talks to its own origin: no CORS preflight,
 * and API traffic never leaves Render's network.
 *
 * Unused on the Vercel fallback deployment, where NEXT_PUBLIC_API_BASE points
 * the browser straight at the public API origin.
 */
import { type NextRequest, NextResponse } from "next/server";

// Reads env per request, so `next build` never needs to know the API host.
export const dynamic = "force-dynamic";

function upstream(): string | null {
  const host = process.env.API_HOST;
  if (!host) return null;
  return `http://${host}:${process.env.API_PORT ?? "10000"}`;
}

// Hop-by-hop and origin-specific headers that must not be replayed upstream.
// `expect` matters in practice: clients send `Expect: 100-continue` on larger
// uploads (a Green Button XML), and undici rejects the whole request if it is
// forwarded. `content-length` is stripped because fetch recomputes it.
const STRIP = new Set([
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "content-length",
  "expect",
  "te",
  "trailer",
  "proxy-authorization",
  "proxy-connection",
]);

async function proxy(req: NextRequest, path: string[]) {
  const base = upstream();
  if (!base) {
    return NextResponse.json(
      { detail: "API host not configured for this deployment." },
      { status: 503 },
    );
  }

  const target = `${base}/api/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!STRIP.has(k.toLowerCase())) headers.set(k, v);
  });
  // The API meters the shared Gemini key per visitor off X-Forwarded-For. Render
  // sets it on the request arriving here; without forwarding it every visitor
  // would share this service's identity and one budget between them.
  const fwd = req.headers.get("x-forwarded-for");
  if (fwd) headers.set("x-forwarded-for", fwd);

  // Buffered rather than streamed: a streaming body needs duplex:"half" and
  // gains nothing here — the largest upload is a Green Button XML.
  const body =
    req.method === "GET" || req.method === "HEAD"
      ? undefined
      : await req.arrayBuffer();

  let res: Response;
  try {
    res = await fetch(target, { method: req.method, headers, body, cache: "no-store" });
  } catch (e) {
    console.error(`[proxy] ${req.method} ${target} failed:`, e);
    return NextResponse.json(
      { detail: "The forecast service is unreachable right now." },
      { status: 502 },
    );
  }

  const out = new Headers(res.headers);
  out.delete("content-encoding");
  out.delete("content-length");
  return new NextResponse(res.body, { status: res.status, headers: out });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
