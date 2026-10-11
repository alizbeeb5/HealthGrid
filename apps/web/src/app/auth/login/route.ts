import { allowedAuthOrigins, authConfigurationError } from "../../../lib/auth/config";
import { NextResponse } from "next/server";
import { createSession, credentialsMatch, returnPath, SESSION_COOKIE, sessionOptions } from "../../../lib/auth/session";

let windowStart = 0;
let attempts = 0;
export async function POST(request: Request) {
  const now = Date.now();
  if (now - windowStart >= 60_000) { windowStart = now; attempts = 0; }
  if (++attempts > 20) return NextResponse.json({ error: "Too many sign-in attempts. Try again in one minute." }, { status: 429, headers: { "Retry-After": "60" } });
  // Also enforce here: route handlers must stay guarded if proxy is bypassed.
  const origins = allowedAuthOrigins();
  const configurationError = authConfigurationError();
  if (!origins || configurationError) return NextResponse.json({ error: configurationError ?? "Secure origins are not configured." }, { status: 503 });
  if (!origins.includes(request.headers.get("origin") ?? "") || request.headers.get("sec-fetch-site") === "cross-site") return NextResponse.json({ error: "Sign in from this website." }, { status: 403 });
  if (!request.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error: "Invalid request." }, { status: 415 });
  if (!process.env.SECURITY_PASSWORD) return NextResponse.json({ error: "Sign-in is not configured." }, { status: 503 });
  const reader = request.body?.getReader();
  if (!reader) return NextResponse.json({ error: "Enter your username and password." }, { status: 400 });
  let length = 0;
  const chunks: Uint8Array[] = [];
  const deadline = setTimeout(() => { void reader.cancel(); }, 5000);
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 4096) { await reader.cancel(); return NextResponse.json({ error: "Request is too large." }, { status: 413 }); }
      chunks.push(value);
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (typeof body.username !== "string" || typeof body.password !== "string" || body.username.length > 128 || body.password.length > 256 || !credentialsMatch(body.username.trim(), body.password)) return NextResponse.json({ error: "The username or password is incorrect." }, { status: 401 });
    const response = NextResponse.json({ redirect: returnPath(body.returnTo) }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(SESSION_COOKIE, createSession(), sessionOptions());
    return response;
  } catch { return NextResponse.json({ error: "Could not sign in. Check your details and try again." }, { status: 400 }); }
  finally { clearTimeout(deadline); reader.releaseLock(); }
}
