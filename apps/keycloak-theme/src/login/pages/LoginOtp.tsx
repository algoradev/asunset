/**
 * LoginOtp — the TOTP prompt shown on every login for users who have
 * MFA enabled. Keycloak submits this form to `url.loginAction` with the
 * field `otp` (and optionally `selectedCredentialId` when the user has
 * multiple registered authenticators).
 */

import { useState, type FormEventHandler } from "react";
import { OTPInput } from "input-otp";
import { clsx } from "keycloakify/tools/clsx";
import type { PageProps } from "keycloakify/login/pages/PageProps";
import type { KcContext } from "../KcContext";
import type { I18n } from "../i18n";

export default function LoginOtp(
  props: PageProps<Extract<KcContext, { pageId: "login-otp.ftl" }>, I18n>,
) {
  const { kcContext, i18n, Template, classes, doUseDefaultCss } = props;
  const { url, messagesPerField, otpLogin } = kcContext;
  const { msg, msgStr } = i18n;

  const [otp, setOtp] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const invalid = messagesPerField.existsError("totp") || messagesPerField.existsError("otp");
  const credentials = otpLogin.userOtpCredentials ?? [];
  const needsCredentialPick = credentials.length > 1;

  const onSubmit: FormEventHandler<HTMLFormElement> = () => {
    setSubmitting(true);
  };

  return (
    <Template
      kcContext={kcContext}
      i18n={i18n}
      doUseDefaultCss={doUseDefaultCss}
      classes={classes}
      displayMessage={!invalid}
      headerNode={msg("doLogIn")}
    >
      <form action={url.loginAction} method="post" onSubmit={onSubmit}>
        {needsCredentialPick && (
          <div className="asunset-field">
            <label className="asunset-label">{msg("loginOtpOneTime")}</label>
            <div>
              {credentials.map((cred) => (
                <label
                  key={cred.id}
                  className="asunset-checkbox"
                  style={{ display: "flex", marginBottom: "0.25rem" }}
                >
                  <input
                    type="radio"
                    name="selectedCredentialId"
                    value={cred.id}
                    defaultChecked={cred.id === otpLogin.selectedCredentialId}
                  />
                  {cred.userLabel}
                </label>
              ))}
            </div>
          </div>
        )}

        <div className="asunset-field">
          <label htmlFor="otp" className="asunset-label">
            {msg("loginOtpOneTime")}
          </label>
          <OTPInput
            id="otp"
            name="otp"
            maxLength={6}
            value={otp}
            onChange={setOtp}
            autoFocus
            autoComplete="one-time-code"
            inputMode="numeric"
            containerClassName="asunset-otp-grid"
            render={({ slots }) => (
              <>
                {slots.map((slot, i) => (
                  <div
                    key={i}
                    className={clsx(
                      "asunset-otp-slot",
                      slot.isActive && "asunset-otp-slot--active",
                    )}
                    data-invalid={invalid ? "true" : undefined}
                  >
                    {slot.char}
                    {slot.hasFakeCaret && (
                      <span className="asunset-otp-caret" />
                    )}
                  </div>
                ))}
              </>
            )}
          />
          {invalid && (
            <div
              className="asunset-alert asunset-alert--error"
              style={{ marginTop: "0.5rem" }}
            >
              <span
                dangerouslySetInnerHTML={{
                  __html:
                    messagesPerField.getFirstError("totp", "otp") ||
                    msgStr("invalidTotpMessage"),
                }}
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          className="asunset-button"
          disabled={otp.length < 6 || submitting}
        >
          {msgStr("doLogIn")}
        </button>
      </form>
    </Template>
  );
}
