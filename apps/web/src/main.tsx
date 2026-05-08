import React from "react";
import ReactDOM from "react-dom/client";
import { AuthProvider } from "react-oidc-context";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";

import App from "./App";
import { oidcConfig } from "./auth";
import { BRAND } from "./config/brand";
import "./i18n";
import "./index.css";

// Runtime title sync — covers the case where Vite couldn't substitute
// `%VITE_BRAND_NAME%` in index.html (env unset during local `npm run dev`
// without a .env). In normal builds the substitution wins; this just
// ensures the tab title matches BRAND.name even in the degenerate case.
document.title = BRAND.name;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <AuthProvider {...oidcConfig}>
        <QueryClientProvider client={queryClient}>
          <App />
          <Toaster richColors closeButton position="top-right" />
        </QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
