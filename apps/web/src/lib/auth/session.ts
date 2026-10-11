import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "healthgrid_session";
export const SESSION_SECONDS = 8 * 60 * 60;
export function credentialsMatch(username: string, password: string) {
  const digest = (value: string) => createHash("sha256").update(value).digest();
  const userMatches = timingSafeEqual(digest(username), digest(process.env.SECURITY_USERNAME ?? "healthgrid"));
  const passwordMatches = timingSafeEqual(digest(password), digest(process.env.SECURITY_PASSWORD ?? ""));
  return Boolean(process.env.SECURITY_PASSWORD) && userMatches && passwordMatches;
}
function signature(value: string) {
  const secret = process.env.SECURITY_SESSION_SECRET ?? "";
  if (secret.length < 32) throw new Error("Session access is not configured.");
  return createHmac("sha256", secret).update(`${process.env.SECURITY_USERNAME ?? "healthgrid"}\0${process.env.SECURITY_PASSWORD}\0${value}`).digest("base64url");
}
export function createSession(now = Date.now()) {
  const value = `${Math.floor(now / 1000) + SESSION_SECONDS}.${randomBytes(24).toString("base64url")}`;
  return `${value}.${signature(value)}`;
}
export function validSession(token: string, now = Date.now()) {
  if (!process.env.SECURITY_PASSWORD || token.length > 256) return false;
  const parts = token.split(".");
  if (parts.length !== 3 || !/^\d{10}$/.test(parts[0]) || !/^[\w-]{32}$/.test(parts[1]) || !/^[\w-]{43}$/.test(parts[2])) return false;
  const expires = Number(parts[0]);
  if (expires <= Math.floor(now / 1000) || expires > Math.floor(now / 1000) + SESSION_SECONDS) return false;
  try { return timingSafeEqual(Buffer.from(parts[2]), Buffer.from(signature(`${parts[0]}.${parts[1]}`))); }
  catch { return false; }
}
export function sessionOptions() {
  return { httpOnly: true, sameSite: "strict" as const, secure: process.env.APP_ENVIRONMENT === "production", path: "/", maxAge: SESSION_SECONDS };
}
export function returnPath(value: unknown) {
  if (typeof value !== "string" || !/^\/(?!\/)/.test(value) || /[\\\r\n\x00]/.test(value) || value.startsWith("/login") || value.startsWith("/auth/")) return "/overview";
  return value;
}
