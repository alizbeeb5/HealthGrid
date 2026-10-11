import { allowedAuthOrigins } from "../../../lib/auth/config";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, sessionOptions } from "../../../lib/auth/session";
export async function POST(request: Request) {
  const origins = allowedAuthOrigins();
  if (!origins) return NextResponse.json({ error: "Secure origins are not configured." }, { status: 503 });
  if (!origins.includes(request.headers.get("origin") ?? "") || request.headers.get("sec-fetch-site") === "cross-site") return new NextResponse("Cross-site request rejected.", { status: 403 });
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login", "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, "", { ...sessionOptions(), maxAge: 0 });
  return response;
}
