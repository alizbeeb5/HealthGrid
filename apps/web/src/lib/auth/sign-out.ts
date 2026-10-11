// Clear the server-issued cookie before leaving the workspace.
export async function endSession(request: typeof fetch = fetch) {
  const response = await request("/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) throw new Error("Could not sign out. Please try again.");
}
