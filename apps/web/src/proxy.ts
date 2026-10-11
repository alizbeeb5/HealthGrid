import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

// Server-only shared access gate for a private prototype. The backend independently
// verifies credentials; this is not user/role authorization or a WAF.
function authenticated(header: string, username: string, password: string) {
  if (header.length > 4096) return false;
  try {
    const [scheme, token] = header.split(" ");
    if (scheme?.toLowerCase() !== "basic" || !token || !/^[A-Za-z0-9+/]+={0,2}$/.test(token)) return false;
    const decoded = Buffer.from(token, "base64").toString("utf8");
    const split = decoded.indexOf(":");
    if (split < 0) return false;
    const digest = (value: string) => createHash("sha256").update(value).digest();
    const validUser = timingSafeEqual(digest(decoded.slice(0, split)), digest(username));
    const validPassword = timingSafeEqual(digest(decoded.slice(split + 1)), digest(password));
    return validUser && validPassword;
  } catch { return false; }
}

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.length > 2048 || request.nextUrl.search.length > 4097) {
    return new NextResponse("Request URI exceeds the size limit.", { status: 414 });
  }
  const production = process.env.APP_ENVIRONMENT === "production";
  const password = process.env.SECURITY_PASSWORD ?? "";
  const username = process.env.SECURITY_USERNAME ?? "healthgrid";
  if ((production && !password) || (password && (password.length < 16 || !username.trim()))) {
    return new NextResponse("Secure access is not configured.", { status: 503 });
  }
  if (password && !authenticated(request.headers.get("authorization") ?? "", username, password)) {
    return new NextResponse("Authentication required.", { status: 401, headers: {
      "WWW-Authenticate": 'Basic realm="HealthGrid", charset="UTF-8"', "Cache-Control": "no-store",
    } });
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
  const nonce = randomBytes(18).toString("base64");
  const development = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'", `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'", // Leaflet/Recharts require inline positioning styles.
    "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
    "font-src 'self'", `connect-src 'self'${development ? " ws: wss:" : ""}`,
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
  ].join("; ");
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
