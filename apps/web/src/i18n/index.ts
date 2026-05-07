import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import es from "./locales/es.json";

// Supported languages. Adding a new one: drop a JSON under locales/ with
// the same key shape, add it here and to LANGUAGES in src/lib/language.ts.
export const SUPPORTED_LANGUAGES = ["en", "es"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

export const defaultNS = "translation";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "en",
    supportedLngs: SUPPORTED_LANGUAGES,
    defaultNS,
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    interpolation: {
      // React already escapes on render.
      escapeValue: false,
    },
    detection: {
      // localStorage first so the user's last explicit choice sticks;
      // then the browser's navigator languages for first-visit defaults.
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "asunset.lang",
    },
    returnNull: false,
  });

export default i18n;
