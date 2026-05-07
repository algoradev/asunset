import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { Me } from "@/api";

export type SettingsSection =
  | "general"
  | "account"
  | "security"
  | "about";

type Ctx = {
  open: boolean;
  section: SettingsSection;
  openSettings: (section?: SettingsSection) => void;
  closeSettings: () => void;
  setSection: (s: SettingsSection) => void;
  me: Me | null;
  requestLogout: () => void;
};

const SettingsCtx = createContext<Ctx | null>(null);

export function SettingsProvider({
  me,
  onRequestLogout,
  children,
}: {
  me: Me | null;
  onRequestLogout: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<SettingsSection>("general");

  const openSettings = useCallback((s?: SettingsSection) => {
    if (s) setSection(s);
    setOpen(true);
  }, []);

  const closeSettings = useCallback(() => setOpen(false), []);

  const value = useMemo<Ctx>(
    () => ({
      open,
      section,
      openSettings,
      closeSettings,
      setSection,
      me,
      requestLogout: onRequestLogout,
    }),
    [open, section, openSettings, closeSettings, me, onRequestLogout],
  );

  return <SettingsCtx.Provider value={value}>{children}</SettingsCtx.Provider>;
}

export function useSettings(): Ctx {
  const ctx = useContext(SettingsCtx);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
