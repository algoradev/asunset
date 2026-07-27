import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        // Silent-renew iframe callback page (A7 in-memory token posture).
        "silent-renew": path.resolve(__dirname, "silent-renew.html"),
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Option S source-alias (docs/frontend-sdk-decision.md): the SDK
      // ships as TypeScript source; these paths are a contract surface.
      // The /hooks subpath must come FIRST — alias matching is
      // prefix-based and the base entry would otherwise swallow it.
      "@asunset/web-sdk/hooks": path.resolve(
        __dirname,
        "../../packages/web-sdk/src/hooks.ts",
      ),
      "@asunset/web-sdk": path.resolve(
        __dirname,
        "../../packages/web-sdk/src/index.ts",
      ),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
  },
});
