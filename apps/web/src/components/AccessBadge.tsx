import { Crown, Building2, Share2, Users2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";

// Translates the server's `access_path` into a consistent visual cue.
// Kinds track the path naming convention: owner | direct:<rel> |
// team '<name>' as <rel> | organization '<name>' as <rel>.
export function AccessBadge({ path, size = "default" }: { path: string; size?: "default" | "sm" }) {
  const kind = resolve(path);
  const Icon = kind.icon;
  return (
    <Badge variant={kind.variant} size={size} className="capitalize">
      <Icon className="size-3" />
      {kind.label}
    </Badge>
  );
}

function resolve(path: string) {
  if (path === "owner") {
    return { label: "Owner", variant: "default" as const, icon: Crown };
  }
  if (path.startsWith("direct")) {
    const rel = path.replace("direct:", "");
    return { label: `Shared · ${rel}`, variant: "info" as const, icon: Share2 };
  }
  if (path.startsWith("team")) {
    return { label: path, variant: "success" as const, icon: Users2 };
  }
  if (path.startsWith("organization")) {
    return { label: path, variant: "warning" as const, icon: Building2 };
  }
  return { label: path, variant: "soft" as const, icon: Share2 };
}
