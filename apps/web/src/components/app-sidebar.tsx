import * as React from "react";
import { Building2, ScrollText, Shield, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { BRAND } from "@/config/brand";
import { RESOURCE } from "@/config/resource";
import { CONSUMER_ROUTES } from "@/config/routes";
import type { Route } from "@/lib/route";
import { useT } from "@/lib/useT";
import { NavMain, type NavItem } from "@/components/nav-main";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export type AppUserLike = {
  display_name: string;
  email: string;
};

export function AppSidebar({
  me,
  route,
  onNavigate,
  onSignOut,
  ...props
}: {
  me: {
    user: AppUserLike;
    realm_roles: string[];
    org_role: "admin" | "member" | null;
  };
  route: Route;
  onNavigate: (r: Route) => void;
  onSignOut: () => void;
} & React.ComponentProps<typeof Sidebar>) {
  const { t } = useT();
  const isPlatformAdmin = me.realm_roles.includes("platform_admin");
  const orgRole = me.org_role;

  const items: NavItem[] = [
    { key: RESOURCE.routeKey, label: t("nav.notes"), icon: RESOURCE.icon },
    { key: "teams", label: t("nav.teams"), icon: Users },
    { key: "org", label: t("nav.org"), icon: Building2 },
    { key: "audit", label: t("nav.audit"), icon: ScrollText },
  ];
  for (const r of CONSUMER_ROUTES) {
    if (r.visible && !r.visible({ isPlatformAdmin, orgRole })) continue;
    items.push({ key: r.key, label: t(r.labelKey), icon: r.icon });
  }
  if (isPlatformAdmin) {
    items.push({ key: "admin", label: t("nav.admin"), icon: Shield });
  }

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              onClick={() => onNavigate(RESOURCE.routeKey)}
            >
              <BrandMark />
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{BRAND.name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {isPlatformAdmin ? t("nav.platformAdmin") : t("nav.memberBadge")}
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={items} activeKey={route} onNavigate={onNavigate} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={me.user} onSignOut={onSignOut} />
      </SidebarFooter>
    </Sidebar>
  );
}

function BrandMark(): JSX.Element {
  const Icon: LucideIcon = RESOURCE.icon;
  return (
    <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
      <Icon className="size-4" />
    </div>
  );
}
