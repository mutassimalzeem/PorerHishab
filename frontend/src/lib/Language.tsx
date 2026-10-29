import { useEffect } from "react";
import type { ReactNode } from "react";
import { t } from "./locale";
import { useLanguage } from "./useLanguage";
export function LanguageProvider({ children }: { children: ReactNode }) {
  const { language } = useLanguage();
  useEffect(() => {
    document.documentElement.lang = language;
    const controls = () =>
      document.querySelectorAll<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >("input, select, textarea");
    controls().forEach((control) => control.setCustomValidity(""));
    const isControl = (
      value: EventTarget | null,
    ): value is HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement =>
      value instanceof HTMLInputElement ||
      value instanceof HTMLSelectElement ||
      value instanceof HTMLTextAreaElement;
    const invalid = (event: Event) => {
      if (isControl(event.target))
        event.target.setCustomValidity(
          event.target.validity.valueMissing
            ? t("Please fill out this field.")
            : t("Please enter a valid value."),
        );
    };
    const input = (event: Event) => {
      if (isControl(event.target)) event.target.setCustomValidity("");
    };
    document.addEventListener("invalid", invalid, true);
    document.addEventListener("input", input, true);
    return () => {
      document.removeEventListener("invalid", invalid, true);
      document.removeEventListener("input", input, true);
    };
  }, [language]);
  return children;
}
export function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage();
  return (
    <div
      className="language-switcher"
      role="group"
      aria-label={t("Interface language")}
    >
      <button
        type="button"
        lang="en"
        aria-pressed={language === "en"}
        onClick={() => setLanguage("en")}
      >
        EN
      </button>
      <button
        type="button"
        lang="bn"
        aria-pressed={language === "bn"}
        onClick={() => setLanguage("bn")}
      >
        {"\u09ac\u09be\u0982\u09b2\u09be"}
      </button>
    </div>
  );
}
