import { useEffect, useState } from "react";

export type Route = "notes" | "teams" | "org" | "audit" | "admin";

const DEFAULT: Route = "notes";
const VALID: readonly Route[] = ["notes", "teams", "org", "audit", "admin"];

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
