import { useQuery } from "@tanstack/react-query";
import { useFetcher } from "@asunset/web-sdk";

import { api } from "@/api";
import { BRAND } from "@/config/brand";
import { useT } from "@/lib/useT";
import { SettingRow, SettingRowGroup } from "../SettingRow";

export function AboutSection() {
  const { t } = useT();
  const f = useFetcher();

  const orgQ = useQuery({
    queryKey: ["org"],
    queryFn: () => api.getOrg(f),
    staleTime: 60_000,
  });

  return (
    <SettingRowGroup>
      <SettingRow
        label={t("settings.about.instance")}
        helper={t("settings.about.instanceHint")}
      >
        <span className="text-sm font-medium">
          {orgQ.data?.name ?? BRAND.name}
        </span>
      </SettingRow>
      <SettingRow
        label={t("settings.about.compliance")}
        helper={t("settings.about.complianceHint")}
      />
      <SettingRow label={t("settings.about.version")}>
        <span className="font-mono text-xs text-muted-foreground">
          {t("settings.about.versionPlaceholder")}
        </span>
      </SettingRow>
    </SettingRowGroup>
  );
}
