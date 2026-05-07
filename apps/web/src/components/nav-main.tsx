import type { LucideIcon } from "lucide-react";

import type { Route } from "@/lib/route";
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export type NavItem = {
  key: Route;
  label: string;
  icon: LucideIcon;
};

export function NavMain({
  items,
  activeKey,
  onNavigate,
}: {
  items: NavItem[];
  activeKey: Route;
  onNavigate: (key: Route) => void;
}) {
  return (
    <SidebarGroup>
      <SidebarMenu>
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <SidebarMenuItem key={item.key}>
              <SidebarMenuButton
                isActive={activeKey === item.key}
                tooltip={item.label}
                onClick={() => onNavigate(item.key)}
              >
                <Icon />
                <span>{item.label}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}
