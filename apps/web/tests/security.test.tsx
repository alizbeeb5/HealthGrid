import assert from "node:assert/strict";
import { test } from "node:test";
import { NextRequest } from "next/server";
import { renderToStaticMarkup } from "react-dom/server";
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
      assert.equal(proxy(new NextRequest(`http://localhost:3000${path}`)).status, 401);
    }
    const header = `Basic ${Buffer.from("healthgrid:test-only-strong-password-123").toString("base64")}`;
    assert.equal(proxy(new NextRequest("http://localhost:3000/facilities", { headers: { authorization: header } })).status, 200);
    assert.equal(proxy(new NextRequest("http://localhost:3000/facilities", { headers: { authorization: "Basic !!!" } })).status, 401);
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
