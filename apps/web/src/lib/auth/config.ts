/** Shared server-only login policy. Never import this module into client components. */
export function authConfigurationError(): string | null {
  const production = process.env.APP_ENVIRONMENT === "production";
  const password = process.env.SECURITY_PASSWORD ?? "";
  const username = process.env.SECURITY_USERNAME ?? "healthgrid";
  if (!password) return production ? "Secure access is not configured." : null;
  if (password.length < (production ? 16 : 12) || !username.trim()) return "Secure access is not configured.";
  if ((process.env.SECURITY_SESSION_SECRET?.length ?? 0) < 32) return "Secure sessions are not configured.";
  return null;
}

export function allowedAuthOrigins(): string[] | null {
  try {
    const values: unknown = JSON.parse(process.env.SECURITY_ALLOWED_ORIGINS ??
      '["http://localhost:3000","http://127.0.0.1:3000","http://localhost:8000","http://127.0.0.1:8000"]');
    if (!Array.isArray(values) || !values.length || values.some((value) => {
      if (typeof value !== "string") return true;
      try {
        const url = new URL(value);
        return !["http:", "https:"].includes(url.protocol) || url.origin !== value ||
          (process.env.APP_ENVIRONMENT === "production" && url.protocol !== "https:");
      } catch { return true; }
    })) return null;
    return values;
  } catch { return null; }
}
