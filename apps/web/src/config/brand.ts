// Product chrome. Driven by env so consumer products can rebrand without
// editing committed TypeScript (every brand-string edit would otherwise
// conflict on every `git subtree pull` from upstream asunset).
//
// Set VITE_BRAND_NAME in your root `.env`; compose passes it through to
// the web build/dev container via the build arg / environment variable
// of the same name. Falls back to "Asunset" so the demo works without
// any env setup.
export const BRAND = {
  name: import.meta.env.VITE_BRAND_NAME || "Asunset",
} as const;
