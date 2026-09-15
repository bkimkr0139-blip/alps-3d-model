// Localized string helpers for data that does not go through i18next:
// (1) bundled fixture data (ASIC/EDA training) ships as {ko,en,ja} triplets,
// (2) demo-dataset strings live in PostgreSQL in the seed's authoring language
// (Korean) and backend rule messages are composed server-side — both are
// overlaid at render time by seedTr (see seedL10n). UI chrome keeps using
// i18next t(); these helpers only cover the data layer.

export type LStr = { ko: string; en: string; ja: string };

export const L = (ko: string, en: string, ja: string): LStr => ({ ko, en, ja });

/** Resolve an LStr to the ui language, English as the neutral fallback. */
export function pickL(v: LStr, lang: string | null | undefined): string {
  if (lang === "ko") return v.ko;
  if (lang === "ja") return v.ja;
  return v.en;
}

/** Data fields may stay a technical string (fab ids, standards names) or be
 * localized prose — this accepts both so files stay readable. */
export type LStrLike = string | LStr;

export function pickText(v: LStrLike, lang: string | null | undefined): string {
  return typeof v === "string" ? v : pickL(v, lang);
}
