import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Info, Settings as SettingsIcon, ShieldCheck, User as UserIcon, X } from "lucide-react";

import { useT } from "@/lib/useT";
import { cn } from "@/lib/utils";
import { AccountSection } from "./sections/AccountSection";
import { GeneralSection } from "./sections/GeneralSection";
import { SecuritySection } from "./sections/SecuritySection";
import { AboutSection } from "./sections/AboutSection";
import { useSettings, type SettingsSection } from "./SettingsContext";

export function SettingsDialog() {
  const { open, section, setSection, closeSettings, me } = useSettings();
  const { t } = useT();

  const nav: { key: SettingsSection; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: "general", label: t("settings.navGeneral"), icon: SettingsIcon },
    { key: "account", label: t("settings.navAccount"), icon: UserIcon },
    { key: "security", label: t("settings.navSecurity"), icon: ShieldCheck },
    { key: "about", label: t("settings.navAbout"), icon: Info },
  ];

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(o) => (o ? null : closeSettings())}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%]",
            "w-[calc(100vw-2rem)] max-w-[760px] h-[calc(100vh-2rem)] max-h-[560px]",
            "overflow-hidden rounded-xl border bg-card text-card-foreground shadow-xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          )}
        >
          <DialogPrimitive.Title className="sr-only">
            {t("settings.title")}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            {t("settings.description")}
          </DialogPrimitive.Description>

          <div className="flex h-full">
            <aside className="hidden w-[200px] shrink-0 flex-col border-r bg-muted/30 p-3 sm:flex">
              <div className="px-2 py-2 text-sm font-semibold tracking-tight">
                {t("settings.title")}
              </div>
              <nav className="mt-2 flex flex-col gap-0.5">
                {nav.map((item) => (
                  <NavItem
                    key={item.key}
                    icon={item.icon}
                    label={item.label}
                    active={section === item.key}
                    onClick={() => setSection(item.key)}
                  />
                ))}
              </nav>
            </aside>

            <div className="flex min-w-0 flex-1 flex-col">
              <header className="flex shrink-0 items-center justify-between border-b px-5 py-3">
                <div className="flex items-center gap-2">
                  <MobileNav
                    value={section}
                    onChange={setSection}
                    items={nav}
                  />
                  <h2 className="text-sm font-semibold">
                    {labelFor(section, nav)}
                  </h2>
                </div>
                <DialogPrimitive.Close
                  className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  aria-label={t("common.close")}
                >
                  <X className="size-4" />
                </DialogPrimitive.Close>
              </header>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {section === "general" && <GeneralSection />}
                {section === "account" && me && <AccountSection me={me} />}
                {section === "security" && <SecuritySection />}
                {section === "about" && <AboutSection />}
              </div>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function NavItem({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
        active
          ? "bg-accent font-medium text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <Icon className="size-4" />
      {label}
    </button>
  );
}

function MobileNav({
  value,
  onChange,
  items,
}: {
  value: SettingsSection;
  onChange: (s: SettingsSection) => void;
  items: {
    key: SettingsSection;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }[];
}) {
  return (
    <select
      className="rounded-md border bg-background px-2 py-1 text-xs sm:hidden"
      value={value}
      onChange={(e) => onChange(e.target.value as SettingsSection)}
    >
      {items.map((i) => (
        <option key={i.key} value={i.key}>
          {i.label}
        </option>
      ))}
    </select>
  );
}

function labelFor(
  section: SettingsSection,
  nav: { key: SettingsSection; label: string }[],
): string {
  return nav.find((n) => n.key === section)?.label ?? "";
}
