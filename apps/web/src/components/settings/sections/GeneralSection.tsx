import { useTheme } from "next-themes";

import { LANGUAGES } from "@/lib/language";
import { useT } from "@/lib/useT";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SettingRow, SettingRowGroup } from "../SettingRow";

export function GeneralSection() {
  const { t, i18n } = useT();
  const { theme, setTheme } = useTheme();
  const currentLang = i18n.language?.split("-")[0] ?? "en";

  return (
    <SettingRowGroup>
      <SettingRow
        label={t("settings.general.theme")}
        helper={t("settings.general.themeHint")}
      >
        <Select value={theme ?? "system"} onValueChange={setTheme}>
          <SelectTrigger className="h-9 w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="light">{t("nav.light")}</SelectItem>
            <SelectItem value="dark">{t("nav.dark")}</SelectItem>
            <SelectItem value="system">{t("nav.system")}</SelectItem>
          </SelectContent>
        </Select>
      </SettingRow>

      <SettingRow
        label={t("settings.general.language")}
        helper={t("settings.general.languageHint")}
      >
        <Select
          value={currentLang}
          onValueChange={(v) => i18n.changeLanguage(v)}
        >
          <SelectTrigger className="h-9 w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((l) => (
              <SelectItem key={l.code} value={l.code}>
                {l.native}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SettingRow>
    </SettingRowGroup>
  );
}
