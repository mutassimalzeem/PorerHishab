import { bn, type TranslationKey } from "./translations";
export type Language = "en" | "bn";
export const languageStorageKey = "porerhishab.language";
export function readLanguage(): Language {
  try {
    return localStorage.getItem(languageStorageKey) === "bn" ? "bn" : "en";
  } catch {
    return "en";
  }
}
let language: Language = readLanguage();
const listeners = new Set<() => void>();
export const getLanguage = () => language;
export const getLocale = () => (language === "bn" ? "bn-BD" : "en-BD");
export function setLanguage(next: Language) {
  if (next !== "en" && next !== "bn") return;
  language = next;
  try {
    localStorage.setItem(languageStorageKey, next);
  } catch {
    /* Private browsing may disable storage. */
  }
  if (typeof document !== "undefined") document.documentElement.lang = next;
  listeners.forEach((listener) => listener());
}
export function subscribeLanguage(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
/** Only call with frontend-owned copy; never pass API prose or user content. */
export function t(key: TranslationKey): string {
  return language === "bn" ? bn[key] : key;
}
/** For frontend-owned labels selected dynamically from navigation/status maps. */
export function uiLabel(key: string): string {
  if (Object.hasOwn(bn, key))
    return language === "en"
      ? key.replaceAll("_", " ")
      : t(key as TranslationKey);
  const source = (Object.keys(bn) as TranslationKey[]).find(
    (source) => bn[source] === key,
  );
  return source ? t(source) : key;
}
export function digits(value: string | number): string {
  return language === "bn"
    ? String(value).replace(/[0-9]/g, (n) =>
        String.fromCharCode(0x09e6 + Number(n)),
      )
    : String(value);
}
export function count(value: number): string {
  return new Intl.NumberFormat(getLocale()).format(value);
}
export function percent(value: number, decimals = 0): string {
  return new Intl.NumberFormat(getLocale(), {
    style: "percent",
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

/** Error prose has a localized recovery fallback when no known message exists. */
export function errorText(message: string): string {
  const translated = uiLabel(message);
  if (
    language === "en" ||
    translated !== message ||
    Object.values(bn).some((value) => value === message)
  )
    return translated;
  return t("The request could not be completed. Please try again.");
}
