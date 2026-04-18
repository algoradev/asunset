/**
 * Custom login Template — the outer frame every login page renders inside.
 *
 * Replaces Keycloak's stock PatternFly-based template with a shadcn-style
 * centered card matching the main web app's visual language. Individual
 * page overrides (Login.tsx, etc.) plug into `children`.
 */

import { useEffect } from "react";
import { clsx } from "keycloakify/tools/clsx";
import { kcSanitize } from "keycloakify/lib/kcSanitize";
import { useInitialize } from "keycloakify/login/Template.useInitialize";
import type { TemplateProps } from "keycloakify/login/TemplateProps";
import type { KcContext } from "./KcContext";
import type { I18n } from "./i18n";

export default function Template(props: TemplateProps<KcContext, I18n>) {
  const {
    kcContext,
    i18n,
    doUseDefaultCss,
    classes,
    displayInfo = false,
    displayMessage = true,
    displayRequiredFields = false,
    headerNode,
    socialProvidersNode = null,
    infoNode = null,
    documentTitle,
    bodyClassName,
    children,
  } = props;

  const { msg, msgStr, currentLanguage, enabledLanguages } = i18n;
  const { realm, auth, message, isAppInitiatedAction } = kcContext;

  useEffect(() => {
    document.title =
      documentTitle ?? msgStr("loginTitle", kcContext.realm.displayName);
  }, [documentTitle, kcContext.realm.displayName, msgStr]);

  const { isReadyToRender } = useInitialize({ kcContext, doUseDefaultCss });
  if (!isReadyToRender) return null;

  const showUsername =
    auth?.showUsername && !auth?.showResetCredentials;

  return (
    <div className={clsx("asunset-shell", bodyClassName)}>
      <div className="asunset-card">
        <div className="asunset-brand">
          <div className="asunset-brand__mark" aria-hidden />
          <h1 className="asunset-brand__title">
            {realm.displayName || "Asunset"}
          </h1>
          {enabledLanguages.length > 1 && (
            <p className="asunset-brand__subtitle">
              {currentLanguage.label}
            </p>
          )}
        </div>

        {showUsername ? (
          <>
            <div className="asunset-header">{auth.attemptedUsername}</div>
            <div className="asunset-sub">
              <a
                href={kcContext.url.loginRestartFlowUrl}
                className="asunset-link"
              >
                {msg("restartLoginTooltip")}
              </a>
            </div>
          </>
        ) : (
          <h2 className="asunset-header">{headerNode}</h2>
        )}

        {displayRequiredFields && (
          <p className="asunset-sub" style={{ textAlign: "left" }}>
            <span style={{ color: "var(--asunset-destructive)" }}>*</span>{" "}
            {msg("requiredFields")}
          </p>
        )}

        {displayMessage && message !== undefined && (message.type !== "warning" || !isAppInitiatedAction) && (
          <div
            className={clsx(
              "asunset-alert",
              message.type === "error" && "asunset-alert--error",
              message.type === "warning" && "asunset-alert--warning",
              message.type === "info" && "asunset-alert--info",
              message.type === "success" && "asunset-alert--info",
            )}
          >
            <span
              dangerouslySetInnerHTML={{
                __html: kcSanitize(message.summary),
              }}
            />
          </div>
        )}

        {children}

        {auth?.showTryAnotherWayLink && (
          <form
            id="kc-select-try-another-way-form"
            action={kcContext.url.loginAction}
            method="post"
            style={{ marginTop: "0.75rem" }}
          >
            <input type="hidden" name="tryAnotherWay" value="on" />
            <button type="submit" className="asunset-link">
              {msg("doTryAnotherWay")}
            </button>
          </form>
        )}

        {socialProvidersNode}

        {displayInfo && <div className="asunset-footer">{infoNode}</div>}
      </div>
    </div>
  );

  // Unused params kept to satisfy TemplateProps discriminated-union width;
  // silence no-unused-vars without rewriting the prop contract.
  void classes;
}
