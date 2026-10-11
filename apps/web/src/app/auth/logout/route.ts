import { NextResponse } from "next/server";
import { SESSION_COOKIE, sessionOptions } from "../../../lib/auth/session";
export async function POST(request: Request) {
  const origins = JSON.parse(process.env.SECURITY_ALLOWED_ORIGINS ?? '["http://localhost:3000","http://127.0.0.1:3000"]') as string[];
  if (!origins.includes(request.headers.get("origin") ?? "") || request.headers.get("sec-fetch-site") === "cross-site") return new NextResponse("Cross-site request rejected.", { status: 403 });
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login", "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, "", { ...sessionOptions(), maxAge: 0 });
  return response;
}
