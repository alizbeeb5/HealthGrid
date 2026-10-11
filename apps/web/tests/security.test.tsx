import assert from "node:assert/strict";
import { test } from "node:test";
import { NextRequest } from "next/server";
import { renderToStaticMarkup } from "react-dom/server";
import { createSession, validSession, SESSION_COOKIE, returnPath } from "../src/lib/auth/session";
import { POST as login } from "../src/app/auth/login/route";
import { POST as logout } from "../src/app/auth/logout/route";
import SignInPage from "../src/app/login/page";
import { endSession } from "../src/lib/auth/sign-out";
import { proxy } from "../src/proxy";
import { HospitalTable } from "../src/features/network/hospital-table";
import { overviewReturnPath } from "../src/features/network/return-navigation";
import example from "../../../contracts/examples/feature-3/emergency-care.overview.response.json";
import type { NetworkOverviewResponse } from "../src/lib/api/network";

function withEnvironment(values: Record<string, string>, work: () => void) {
  const previous = { ...process.env };
  try {
    delete process.env.SECURITY_PASSWORD;
    delete process.env.SECURITY_ALLOWED_ORIGINS;
    process.env.APP_ENVIRONMENT = "development";
    process.env.SECURITY_SESSION_SECRET = "independent-test-session-secret-1234567890";
    Object.assign(process.env, values);
    work();
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
  }
}

test("frontend production gate is closed without credentials and checks every API request", () => {
  withEnvironment({ APP_ENVIRONMENT: "production" }, () => {
    assert.equal(proxy(new NextRequest("http://localhost:3000/facilities")).status, 503);
  });
  withEnvironment({ SECURITY_PASSWORD: "test-only-strong-password-123" }, () => {
    for (const path of ["/facilities", "/api/v1/demo", "/api/v1/decisions"]) {
      assert.equal(proxy(new NextRequest(`http://localhost:3000${path}`)).status, path.startsWith("/api/") ? 401 : 307);
    }
    const cookie = `${SESSION_COOKIE}=${createSession()}`;
    assert.equal(proxy(new NextRequest("http://localhost:3000/facilities", { headers: { cookie } })).status, 200);
    assert.equal(proxy(new NextRequest("http://localhost:3000/facilities", { headers: { authorization: "Basic !!!" } })).status, 307);
    const response = proxy(new NextRequest("http://localhost:3000/api/v1/demo", { headers: { cookie } }));
    assert.equal(response.headers.get("x-middleware-request-authorization"), `Basic ${Buffer.from("healthgrid:test-only-strong-password-123").toString("base64")}`);
    assert.equal(proxy(new NextRequest("http://localhost:3000/login")).status, 200);
  });
});

test("cross-site mutations, oversized declared bodies and excessive URIs are blocked", () => {
  withEnvironment({}, () => {
    assert.equal(proxy(new NextRequest("http://localhost:3000/api/v1/decisions", { method: "POST", headers: { origin: "https://evil.example" } })).status, 403);
    assert.equal(proxy(new NextRequest("http://localhost:3000/api/v1/decisions", { method: "POST", headers: { "content-length": "9999999" } })).status, 413);
    assert.equal(proxy(new NextRequest(`http://localhost:3000/facilities?q=${"a".repeat(5000)}`)).status, 414);
  });
});

test("production CSP uses fresh nonces, disallows script eval, objects and framing", () => {
  withEnvironment({ NODE_ENV: "production" }, () => {
    const request = new NextRequest("http://localhost:3000/facilities");
    const first = proxy(request).headers.get("content-security-policy")!;
    const second = proxy(request).headers.get("content-security-policy")!;
    assert.match(first, /script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    assert.match(first, /object-src 'none'/);
    assert.match(first, /frame-ancestors 'none'/);
    assert.doesNotMatch(first, /unsafe-eval/);
    assert.notEqual(first, second);
  });
});

test("hospital report HTML is escaped and return links cannot redirect to an attacker", () => {
  const report = structuredClone(example) as NetworkOverviewResponse;
  report.facilities[0].facility.name = '<script>alert("stolen")</script>';
  const markup = renderToStaticMarkup(<HospitalTable rows={report.facilities} returnTo="/overview" />);
  assert.doesNotMatch(markup, /<script>alert/);
  assert.match(markup, /&lt;script&gt;/);
  for (const target of ["https://evil.example", "//evil.example/overview", "/overview/../evil", "javascript:alert(1)"]) {
    assert.equal(overviewReturnPath(target), undefined);
  }
});


test("signed sessions reject tampering, expiry and changed credentials", () => {
  withEnvironment({ SECURITY_PASSWORD: "test-only-strong-password-123" }, () => {
    const token = createSession();
    assert.equal(validSession(token), true);
    assert.equal(validSession(token + "x"), false);
    assert.equal(validSession(createSession(Date.now() - 9 * 60 * 60 * 1000)), false);
    process.env.SECURITY_PASSWORD = "different-test-password-123";
    assert.equal(validSession(token), false);
    assert.equal(returnPath("//evil.example"), "/overview");
    assert.equal(returnPath("/\\evil.example"), "/overview");
    assert.equal(returnPath("/facilities/DEMO-B"), "/facilities/DEMO-B");
  });
});

test("sign-in form is accessible and never embeds credentials", () => {
  const markup = renderToStaticMarkup(<SignInPage />);
  assert.match(markup, /autoComplete="current-password"/);
  assert.match(markup, /type="password"/);
  assert.match(markup, /Sign in/);
  assert.doesNotMatch(markup, /SECURITY_PASSWORD/);
  assert.doesNotMatch(markup, /name="password"[^>]*value=/);
});

test("login and logout guard origins and set protected cookies", async () => {
  const previous = { ...process.env };
  Object.assign(process.env, { APP_ENVIRONMENT: "development", SECURITY_PASSWORD: "test-only-strong-password-123", SECURITY_USERNAME: "healthgrid", SECURITY_SESSION_SECRET: "independent-test-session-secret-1234567890" });
  delete process.env.SECURITY_ALLOWED_ORIGINS;
  const request = (password: string, origin = "http://localhost:3000") => new Request("http://localhost:3000/auth/login", { method: "POST", headers: { origin, "content-type": "application/json" }, body: JSON.stringify({ username: "healthgrid", password, returnTo: "https://evil.example" }) });
  try {
    assert.equal((await login(request("wrong"))).status, 401);
    assert.equal((await login(request(process.env.SECURITY_PASSWORD!, "https://evil.example"))).status, 403);
    const response = await login(request(process.env.SECURITY_PASSWORD!));
    assert.equal(response.status, 200);
    assert.equal((await response.json()).redirect, "/overview");
    const cookie = response.cookies.get(SESSION_COOKIE)!;
    assert.equal(validSession(cookie.value), true);
    assert.equal(cookie.httpOnly, true);
    assert.equal(cookie.sameSite, "strict");
    assert.equal((await logout(new Request("http://localhost:3000/auth/logout", { method: "POST", headers: { origin: "https://evil.example" } }))).status, 403);
    const signedOut = await logout(new Request("http://localhost:3000/auth/logout", { method: "POST", headers: { origin: "http://localhost:3000" } }));
    assert.equal(signedOut.cookies.get(SESSION_COOKIE)?.maxAge, 0);
    assert.equal(signedOut.headers.get("location"), "/login");
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
  }
});


test("sign-out clears the session using a same-origin POST and surfaces failures", async () => {
  let calls = 0;
  await endSession(async (url, options) => {
    calls++;
    assert.equal(url, "/auth/logout");
    assert.equal(options?.method, "POST");
    assert.equal(options?.credentials, "same-origin");
    assert.equal(options?.body, "{}");
    return new Response(null, { status: 200 });
  });
  assert.equal(calls, 1);
  await assert.rejects(endSession(async () => new Response(null, { status: 403 })), /Could not sign out/);
});
