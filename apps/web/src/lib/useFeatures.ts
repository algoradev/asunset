import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";

import { api } from "@/api";
import type { FeatureKey } from "@/config/features.gen";

/**
 * Feature keys the signed-in user may use (GET /platform/me/features).
 *
 * UX gating only — hide menu items and routes with it, but the API's
 * require_feature dependency is the actual control. While loading, the
 * set is empty: prefer hiding gated chrome until features resolve over
 * flashing it and 403ing.
 *
 *   const { has } = useFeatures();
 *   if (has("audit.view")) { ...render the audit nav item... }
 */
export function useFeatures() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const q = useQuery({
    queryKey: ["me-features"],
    queryFn: () => api.meFeatures({ accessToken: token }),
    enabled: !!token,
    staleTime: 60_000,
  });
  const set = new Set(q.data ?? []);
  return {
    features: set,
    // Typed against the generated union: a typo'd key is a COMPILE error.
    has: (key: FeatureKey) => set.has(key),
    isLoading: q.isLoading,
  };
}
