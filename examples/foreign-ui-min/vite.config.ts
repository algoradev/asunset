import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@asunset/web-sdk": new URL(
        "../../packages/web-sdk/src/index.ts",
        import.meta.url,
      ).pathname,
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/platform": "http://localhost:8000",
      "/orgs": "http://localhost:8000",
    },
  },
  build: {
    rollupOptions: {
      input: {
        app: new URL("./index.html", import.meta.url).pathname,
        silentRenew: new URL("./silent-renew.html", import.meta.url).pathname,
      },
    },
  },
});
