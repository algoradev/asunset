import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import {
  Building2,
  Globe,
  LogOut,
  Monitor,
  Moon,
  ScrollText,
  Settings as SettingsIcon,
  Shield,
  Sun,
  Users,
} from "lucide-react";

import { RESOURCE } from "@/config/resource";
import { CONSUMER_ROUTES } from "@/config/routes";
import { LANGUAGES } from "@/lib/language";
import type { Route } from "@/lib/route";
import { useT } from "@/lib/useT";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";

export function CommandPalette({
  isPlatformAdmin,
  orgRole,
  onNavigate,
  onSignOut,
  onOpenSettings,
}: {
  isPlatformAdmin: boolean;
  orgRole: "admin" | "member" | null;
  onNavigate: (r: Route) => void;
  onSignOut: () => void;
  onOpenSettings: (section?: "general" | "account" | "security" | "about") => void;
}) {
  const [open, setOpen] = useState(false);
  const { setTheme } = useTheme();
  const { t, i18n } = useT();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const run = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder={t("palette.placeholder")} />
      <CommandList>
        <CommandEmpty>{t("palette.empty")}</CommandEmpty>
        <CommandGroup heading={t("palette.navigate")}>
          <CommandItem onSelect={() => run(() => onNavigate(RESOURCE.routeKey))}>
            <RESOURCE.icon />
            {t("palette.gotoNotes")}
            <CommandShortcut>G N</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(() => onNavigate("teams"))}>
            <Users />
            {t("palette.gotoTeams")}
            <CommandShortcut>G T</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(() => onNavigate("org"))}>
            <Building2 />
            {t("palette.gotoOrg")}
            <CommandShortcut>G O</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(() => onNavigate("audit"))}>
            <ScrollText />
            {t("palette.gotoAudit")}
            <CommandShortcut>G A</CommandShortcut>
          </CommandItem>
          {CONSUMER_ROUTES.map((r) => {
            if (r.visible && !r.visible({ isPlatformAdmin, orgRole })) return null;
            const Icon = r.icon;
            return (
              <CommandItem
                key={r.key}
                onSelect={() => run(() => onNavigate(r.key))}
              >
                <Icon />
                {t(r.paletteLabelKey ?? r.labelKey)}
                {r.shortcut && <CommandShortcut>{r.shortcut}</CommandShortcut>}
              </CommandItem>
            );
          })}
          {isPlatformAdmin && (
            <CommandItem onSelect={() => run(() => onNavigate("admin"))}>
              <Shield />
              {t("palette.gotoAdmin")}
            </CommandItem>
          )}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading={t("settings.title")}>
          <CommandItem onSelect={() => run(() => onOpenSettings("general"))}>
            <SettingsIcon />
            {t("palette.openSettings")}
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading={t("palette.theme")}>
          <CommandItem onSelect={() => run(() => setTheme("light"))}>
            <Sun />
            {t("palette.themeLight")}
          </CommandItem>
          <CommandItem onSelect={() => run(() => setTheme("dark"))}>
            <Moon />
            {t("palette.themeDark")}
          </CommandItem>
          <CommandItem onSelect={() => run(() => setTheme("system"))}>
            <Monitor />
            {t("palette.themeSystem")}
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading={t("palette.languageLabel")}>
          {LANGUAGES.map((l) => (
            <CommandItem
              key={l.code}
              onSelect={() => run(() => i18n.changeLanguage(l.code))}
            >
              <Globe />
              {l.native}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading={t("palette.account")}>
          <CommandItem onSelect={() => run(onSignOut)}>
            <LogOut />
            {t("common.signOut")}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
