import { useEffect, useState } from "react";

import { RESOURCE } from "@/config/resource";
import { CONSUMER_ROUTES } from "@/config/routes";

// The resource route key is config-driven (see src/config/resource.ts) so
// that renaming the product's domain resource propagates through the type
// union, URL hash, and sidebar without a grep-and-replace. Consumer-added
// secondary routes flow in via CONSUMER_ROUTES (see src/config/routes.ts).
type PlatformRoute =
  | typeof RESOURCE.routeKey
  | "teams"
  | "org"
  | "audit"
  | "admin";

type ConsumerRouteKey = (typeof CONSUMER_ROUTES)[number]["key"];

export type Route = PlatformRoute | ConsumerRouteKey;

const DEFAULT: Route = RESOURCE.routeKey;
const VALID: readonly Route[] = [
  RESOURCE.routeKey,
  "teams",
  "org",
  "audit",
  "admin",
  ...CONSUMER_ROUTES.map((r) => r.key as ConsumerRouteKey),
];

function parseHash(raw: string): Route {
  const v = raw.replace(/^#/, "");
  return (VALID as readonly string[]).includes(v) ? (v as Route) : DEFAULT;
}

export function useRoute(): [Route, (to: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const navigate = (to: Route) => {
    window.location.hash = to;
  };

  return [route, navigate];
}
