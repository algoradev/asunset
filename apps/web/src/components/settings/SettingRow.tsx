import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// A settings list row. Inline controls on the right, stacked label + optional
// helper on the left. Rows are separated by a soft border so the overall pane
// reads as a list rather than a grid of cards (spec §9).
export function SettingRow({
  label,
  helper,
  children,
  align = "center",
}: {
  label: ReactNode;
  helper?: ReactNode;
  children?: ReactNode;
  align?: "center" | "start";
}) {
  return (
    <div
      className={cn(
        "flex gap-4 border-b border-border/60 py-4 last:border-b-0",
        align === "center" ? "items-center" : "items-start",
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="text-sm font-medium text-foreground">{label}</div>
        {helper && (
          <div className="text-xs leading-relaxed text-muted-foreground">
            {helper}
          </div>
        )}
      </div>
      {children && (
        <div className="flex shrink-0 items-center">{children}</div>
      )}
    </div>
  );
}

export function SettingRowGroup({ children }: { children: ReactNode }) {
  return <div className="flex flex-col">{children}</div>;
}
