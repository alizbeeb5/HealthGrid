/** Browser API client. Next.js proxies /api to FastAPI. */
export async function apiGet<T>(path: `/api/v1/${string}`): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return (await response.json()) as T;
}
