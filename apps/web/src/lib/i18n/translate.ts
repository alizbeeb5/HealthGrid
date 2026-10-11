import arabic from "./ar.json";

export type Locale = "en" | "ar";
export const localeTag = (locale: Locale) => locale === "ar" ? "ar-LB-u-nu-latn" : "en-GB";
const messages: Readonly<Record<string, string>> = arabic;
const patterns = Object.entries(messages).filter(([key]) => /\{\d+\}/.test(key)).map(([key, value]) => ({
  parts: key.split(/\{\d+\}/), value,
}));

// Match catalog templates with bounded string searches, never backtracking regexes
// over arbitrary report text. Placeholders appear in source order ({0}, {1}, ...).
function capture(text: string, parts: string[]): string[] | null {
  if (!text.startsWith(parts[0])) return null;
  const values: string[] = [];
  let cursor = parts[0].length;
  for (let i = 1; i < parts.length; i++) {
    const next = parts[i];
    const last = i === parts.length - 1;
    const end = last ? text.length - next.length : text.indexOf(next, cursor + 1);
    if (end <= cursor || (last && !text.endsWith(next))) return null;
    values.push(text.slice(cursor, end));
    cursor = end + next.length;
  }
  return cursor === text.length ? values : null;
}

/** Presentation only. Never use translated labels as API values or record identifiers. */
export function translateText(text: string, locale: Locale): string {
  if (locale === "en") return text;
  if (text.trim() === "→") return text.replace("→", "←");
  if (!/[A-Za-z]/.test(text)) return text;
  const trimmed = text.trim();
  const direct = Object.hasOwn(messages, trimmed) ? messages[trimmed] : undefined;
  if (direct !== undefined) return text.replace(trimmed, () => direct);
  for (const { parts, value } of patterns) {
    const values = capture(trimmed, parts);
    if (values) return text.replace(trimmed, () => value.replace(/\{(\d+)\}/g, (_, index: string) => translateText(values[Number(index)], locale)));
  }
  // Composed display labels retain numbers, IDs and original free-text evidence.
  const parts = text.split(/(\s+[·→]\s+|; |, |\n)/);
  if (parts.length > 1) return parts.map((part, index) => index % 2 ? part : translateText(part, locale)).join("");
  return text;
}

export function translateValue<T>(value: T, locale: Locale): T {
  if (typeof value === "string") return translateText(value, locale) as T;
  if (Array.isArray(value)) return value.map((entry: unknown) => translateValue(entry, locale)) as T;
  return value;
}
