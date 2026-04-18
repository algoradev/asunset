import { FileText, Shield, ScrollText, Users, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Route } from "@/lib/route";

type Item = { key: Route; label: string; icon: React.ComponentType<{ className?: string }>; gate?: "platform_admin" };

const ITEMS: Item[] = [
  { key: "notes", label: "Notes", icon: FileText },
  { key: "teams", label: "Teams", icon: Users },
  { key: "org", label: "Organization", icon: Building2 },
  { key: "audit", label: "Audit", icon: ScrollText },
  { key: "admin", label: "Admin", icon: Shield, gate: "platform_admin" },
];

export function Sidebar({
  route,
  onNavigate,
  realmRoles,
}: {
  route: Route;
  onNavigate: (r: Route) => void;
  realmRoles: string[];
}) {
  const isPlatformAdmin = realmRoles.includes("platform_admin");
  return (
    <nav className="w-56 shrink-0 border-r py-4 px-2 space-y-1">
      {ITEMS.map((item) => {
        if (item.gate === "platform_admin" && !isPlatformAdmin) return null;
        const Icon = item.icon;
        const active = route === item.key;
        return (
          <button
            key={item.key}
            onClick={() => onNavigate(item.key)}
            className={cn(
              "w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
              active
                ? "bg-secondary text-secondary-foreground font-medium"
                : "hover:bg-accent hover:text-accent-foreground text-muted-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
