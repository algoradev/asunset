import { useEffect } from "react";
import { useTranslation } from "react-i18next";

// Thin wrapper so components can `const { t, i18n } = useT()` without
// importing react-i18next directly. Also keeps <html lang> in sync for
// accessibility + any CSS that branches on :lang().
export function useT() {
  const ctx = useTranslation();
  useEffect(() => {
    const lang = ctx.i18n.language?.split("-")[0] ?? "en";
    if (document.documentElement.lang !== lang) {
      document.documentElement.lang = lang;
    }
  }, [ctx.i18n.language]);
  return ctx;
}
