/** Accept only our overview path. Never navigate to an arbitrary return URL. */
export function overviewReturnPath(value: string | string[] | undefined) {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value, "http://healthgrid.local");
    if (!value.startsWith("/overview") || url.origin !== "http://healthgrid.local" || url.pathname !== "/overview") return undefined;
    return `/overview${url.search}`;
  } catch { return undefined; }
}
