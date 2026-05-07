import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/**
 * Extension point for product-specific routes.
 *
 * The asunset shell (sidebar, command palette, breadcrumb, page-render
 * switch, route type union) reads this array and wires every entry up
 * for free. Adding a route is a one-file edit instead of editing the
 * sidebar, palette, App.tsx, route.ts, and the i18n locales by hand.
 *
 * Use this for **secondary read-only surfaces** in your product
 * (dashboards, KPIs, balances, log views). The platform's own routes —
 * the primary shareable resource (RESOURCE), teams, org, audit, admin
 * — are wired separately and you should not duplicate them here.
 *
 * **Translations.** `labelKey` is an i18n key looked up via `t()`. Add
 * the corresponding strings to every locale you support
 * (apps/web/src/i18n/locales/*.json) — usually under the `nav` and
 * `palette` namespaces, e.g. `nav.deposits` and `palette.gotoDeposits`.
 *
 * **Visibility.** Optional `visible(ctx)` predicate hides a route from
 * the sidebar and palette. Returning false also blocks navigation to
 * that key — direct URL hash entry falls back to the default route.
 */
export type ConsumerRoute = {
  /** URL hash key. Becomes part of the `Route` type union. Keep lowercase + dashes. */
  key: string;
  /** i18n key for the navigation label (e.g. `"nav.deposits"`). */
  labelKey: string;
  /** Sidebar / palette icon. */
  icon: LucideIcon;
  /** Page element to render when the route is active. */
  page: ReactNode;
  /** Optional palette shortcut hint, e.g. `"G D"`. Cosmetic only — no listener is registered. */
  shortcut?: string;
  /** Optional palette label key. Falls back to `labelKey` if omitted. */
  paletteLabelKey?: string;
  /**
   * Optional visibility gate. Receives platform/role flags. Return false
   * to hide the route from sidebar and palette. Default: always visible.
   */
  visible?: (ctx: { isPlatformAdmin: boolean; orgRole: "admin" | "member" | null }) => boolean;
};

/**
 * Wraps a literal `as const` array so consumer route keys flow into the
 * `Route` type union as string literals (instead of widening to `string`).
 *
 * ```ts
 * import { Landmark } from "lucide-react";
 * import { defineConsumerRoutes } from "@/config/routes";
 * import { DepositsPage } from "@/features/deposits/DepositsPage";
 *
 * export const CONSUMER_ROUTES = defineConsumerRoutes([
 *   {
 *     key: "deposits",
 *     labelKey: "nav.deposits",
 *     paletteLabelKey: "palette.gotoDeposits",
 *     icon: Landmark,
 *     page: <DepositsPage />,
 *   },
 * ]);
 * ```
 */
export function defineConsumerRoutes<const T extends readonly ConsumerRoute[]>(routes: T): T {
  return routes;
}

/**
 * Default: no consumer routes. Override this file in your product fork
 * (or copy this module into your product and re-export from `@/config/routes`).
 *
 * The wide annotation here keeps the empty default usable; consumers
 * who want their literal keys to flow into the `Route` type union
 * should replace this with `defineConsumerRoutes([...])` (no annotation).
 */
export const CONSUMER_ROUTES: readonly ConsumerRoute[] = [];
