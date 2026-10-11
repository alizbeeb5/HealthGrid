import { randomBytes } from "node:crypto";
import { SESSION_COOKIE, validSession } from "./lib/auth/session";
import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.length > 2048 || request.nextUrl.search.length > 4097) {
    return new NextResponse("Request URI exceeds the size limit.", { status: 414 });
  }
  const production = process.env.APP_ENVIRONMENT === "production";
  const password = process.env.SECURITY_PASSWORD ?? "";
  const username = process.env.SECURITY_USERNAME ?? "healthgrid";
  if ((production && !password) || (password && (password.length < (production ? 16 : 12) || !username.trim()))) {
    return new NextResponse("Secure access is not configured.", { status: 503 });
  }
  const writes = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  const origin = request.headers.get("origin");
  let allowedOrigins: string[];
  try {
    allowedOrigins = JSON.parse(process.env.SECURITY_ALLOWED_ORIGINS ??
      '["http://localhost:3000","http://127.0.0.1:3000","http://localhost:8000","http://127.0.0.1:8000"]');
    if (!Array.isArray(allowedOrigins) || allowedOrigins.some((value) => typeof value !== "string" || (production && !value.startsWith("https://")))) throw new Error();
  } catch { return new NextResponse("Secure origins are not configured.", { status: 503 }); }
  if (request.headers.get("sec-fetch-site") === "cross-site" || (writes && origin && !allowedOrigins.includes(origin))) {
    return new NextResponse("Cross-site request rejected.", { status: 403 });
  }
  if (writes) {
    const length = request.headers.get("content-length");
    if (length && (!/^\d{1,12}$/.test(length) || Number(length) > 1_048_576)) {
      return new NextResponse("Request exceeds the size limit.", { status: 413 });
    }
  }
  const publicRoute = ["/login", "/auth/login", "/auth/logout"].includes(request.nextUrl.pathname);
  const signedIn = validSession(request.cookies.get(SESSION_COOKIE)?.value ?? "");
  if (password && (process.env.SECURITY_SESSION_SECRET?.length ?? 0) < 32) {
    return new NextResponse("Secure sessions are not configured.", { status: 503 });
  }
  if (password && !publicRoute && !signedIn) {
    if (request.nextUrl.pathname.startsWith("/api/") || writes) {
      return NextResponse.json({ error: { message: "Sign in to continue." } }, { status: 401, headers: { "Cache-Control": "no-store" } });
    }
    const target = new URL("/login", request.url);
    target.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search);
    const redirect = NextResponse.redirect(target);
    redirect.headers.set("Cache-Control", "no-store");
    return redirect;
  }
  const nonce = randomBytes(18).toString("base64");
  const development = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'", `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'", // Leaflet/Recharts require inline positioning styles.
    "img-src 'self' data: blob: https://tile.openstreetmap.org",
    "font-src 'self'", `connect-src 'self'${development ? " ws: wss:" : ""}`,
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
  ].join("; ");
  const headers = new Headers(request.headers);
  // Only the server-to-server API request receives the shared credential.
  if (password && signedIn && request.nextUrl.pathname.startsWith("/api/")) {
    headers.set("authorization", `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`);
    headers.delete("cookie");
  } else { headers.delete("authorization"); }
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
