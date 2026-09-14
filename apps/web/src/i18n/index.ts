import i18n, { type TFunction } from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en, { type Resources } from "./locales/en";
import ko from "./locales/ko";
import ja from "./locales/ja";

// Typed `t()`: the translation resource shape feeds i18next's type options so
// unknown or mistyped keys fail `tsc -b` instead of rendering raw on screen.
declare module "i18next" {
  interface CustomTypeOptions {
    resources: { translation: Resources };
  }
}

// Default language = browser auto-detect (user decision); the header switcher
// writes "alps-lang" explicitly, and detection order makes it win afterwards.
// `load: "languageOnly"` maps ja-JP / ko-KR browser locales onto ja / ko.
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ko: { translation: ko },
      ja: { translation: ja },
    },
    fallbackLng: "en",
    supportedLngs: ["ko", "en", "ja"],
    load: "languageOnly",
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "alps-lang",
      caches: [],
    },
    returnEmptyString: false,
    interpolation: { escapeValue: false },
  });

// Keep <html lang> and the tab title in step with the active language.
export function applyDocumentLanguage(lng: string) {
  document.documentElement.lang = lng;
  document.title = i18n.t("app.title");
}

i18n.on("languageChanged", applyDocumentLanguage);
applyDocumentLanguage(i18n.resolvedLanguage ?? "en");

// Enum values arrive as API data (run.status, requirement.status, checklist
// keys…), so their keys can't be literal-typed. `as never` satisfies the typed
// t() while runtime behavior stays a plain lookup; defaultValue renders
// unknown server values verbatim instead of showing a raw key.
export function enumLabel(t: TFunction, group: string, value: string): string {
  return t(`enums.${group}.${value}` as never, { defaultValue: value });
}

export function checklistLabel(t: TFunction, key: string): string {
  return t(`checklist.${key}` as never, { defaultValue: key });
}

export default i18n;
