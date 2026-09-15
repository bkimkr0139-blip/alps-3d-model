import { useTranslation } from "react-i18next";
import i18n from "./index";

const LANGUAGES = [
  { code: "ko", label: "한국어" },
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
] as const;

export function LanguageSwitcher() {
  const { t } = useTranslation();

  function change(lng: string) {
    // Detection order starts with localStorage, so persisting the choice here
    // makes it stick across reloads; languageChanged triggers <html lang> and
    // document.title updates (see index.ts).
    void i18n.changeLanguage(lng);
    localStorage.setItem("alps-lang", lng);
  }

  return (
    <select
      value={i18n.resolvedLanguage ?? "en"}
      onChange={(e) => change(e.target.value)}
      aria-label={t("app.language")}
      style={{ padding: "6px 10px", borderRadius: 6, background: "#1e293b", color: "white", border: "1px solid #334155", fontFamily: "inherit", fontSize: 13 }}
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
