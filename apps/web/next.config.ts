import type { NextConfig } from "next";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseEnv } from "node:util";

// Next loads apps/web/.env*, whereas FastAPI loads the repository .env.
// Share only these server-side settings. Shell/Docker/app-local values take precedence.
// Never put credentials in Next's `env` option: it bundles values for the browser.
const rootEnvironment = resolve(__dirname, "../../.env");
if (existsSync(rootEnvironment)) {
  const values = parseEnv(readFileSync(rootEnvironment, "utf8"));
  for (const key of ["APP_ENVIRONMENT", "SECURITY_USERNAME", "SECURITY_PASSWORD",
    "SECURITY_SESSION_SECRET", "SECURITY_ALLOWED_ORIGINS", "API_BASE_URL"] as const) {
    if (process.env[key] === undefined && values[key] !== undefined) process.env[key] = values[key];
  }
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  experimental: { proxyClientMaxBodySize: "1mb" },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ] }];
  },
  async rewrites() {
    const api = process.env.API_BASE_URL ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
