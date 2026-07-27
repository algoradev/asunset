import { useFeatureSet } from "@/lib/platformHooks";
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
 *
 * Typed against the generated union: a typo'd key is a COMPILE error.
 */
export function useFeatures() {
  return useFeatureSet<FeatureKey>();
}
