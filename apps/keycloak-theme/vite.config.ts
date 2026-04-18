import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { keycloakify } from "keycloakify/vite-plugin";

// The theme name Keycloak loads at `themes/<name>/login/` comes from
// package.json#name — keep it "asunset" so the realm's `loginTheme`
// attribute matches.
export default defineConfig({
  plugins: [
    react(),
    keycloakify({
      accountThemeImplementation: "none",
    }),
  ],
});
