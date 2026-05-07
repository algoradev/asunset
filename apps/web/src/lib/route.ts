import { useEffect, useState } from "react";

import { RESOURCE } from "@/config/resource";

// The resource route key is config-driven (see src/config/resource.ts) so
// that renaming the product's domain resource propagates through the type
// union, URL hash, and sidebar without a grep-and-replace.
export type Route =
  | typeof RESOURCE.routeKey
  | "teams"
  | "org"
  | "audit"
  | "admin";

const DEFAULT: Route = RESOURCE.routeKey;
const VALID: readonly Route[] = [
  RESOURCE.routeKey,
  "teams",
  "org",
  "audit",
  "admin",
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
