/** Browser transport: never show raw proxy HTML or parse errors as login feedback. */
export async function signInRequest(username: string, password: string, returnTo: string | null) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch("/auth/login", {
      method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username: username.trim(), password, returnTo }),
    });
    const body = await response.json().catch(() => null) as { error?: unknown; redirect?: unknown } | null;
    if (!response.ok) {
      const fallback = response.status === 429 ? "Too many sign-in attempts. Try again in one minute."
        : response.status === 503 ? "Sign-in is unavailable. Check the server configuration and restart the web app."
        : response.status === 403 ? "Sign in from this website."
        : response.status === 401 ? "The username or password is incorrect."
        : "Could not sign in. Try again.";
      const error = typeof body?.error === "string" ? body.error : fallback;
      throw new Error(error);
    }
    if (typeof body?.redirect !== "string" || !/^\/(?!\/)/.test(body.redirect) || /[\\\r\n\x00]/.test(body.redirect)) {
      throw new Error("Could not confirm sign-in. Please try again.");
    }
    return body.redirect;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Sign-in timed out. Check your connection and try again.");
    if (error instanceof TypeError) throw new Error("Could not connect. Try again.");
    throw error;
  } finally { clearTimeout(timeout); }
}
