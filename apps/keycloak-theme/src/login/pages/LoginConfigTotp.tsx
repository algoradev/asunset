/**
 * LoginConfigTotp — the TOTP enrollment page, shown the first time a user
 * logs in against a realm with `CONFIGURE_TOTP` as a required action.
 *
 * Keycloak hands us either a QR code (png, base64) or a manual text
 * secret depending on the `mode` query parameter. We render the opposite
 * as a link so the user can switch. Both branches submit the same form
 * with the verification code, the secret (echoed back so Keycloak can
 * verify), and an optional device label.
 */

import { useState, type FormEventHandler } from "react";
import { OTPInput } from "input-otp";
import { clsx } from "keycloakify/tools/clsx";
import type { PageProps } from "keycloakify/login/pages/PageProps";
import type { KcContext } from "../KcContext";
import type { I18n } from "../i18n";

export default function LoginConfigTotp(
  props: PageProps<Extract<KcContext, { pageId: "login-config-totp.ftl" }>, I18n>,
) {
  const { kcContext, i18n, Template, classes, doUseDefaultCss } = props;
  const { url, totp, mode, messagesPerField, isAppInitiatedAction } = kcContext;
  const { msg, msgStr, advancedMsg } = i18n;

  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const invalid = messagesPerField.existsError("totp");
  const existingCredentials = totp.otpCredentials ?? [];
  const labelRequired = existingCredentials.length >= 1;
  const isManual = mode === "manual";

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
      headerNode={msg("loginTotpTitle")}
    >
      <ol className="asunset-totp-steps">
        <li>
          {msg("loginTotpStep1")}
          {totp.supportedApplications && totp.supportedApplications.length > 0 && (
            <ul>
              {totp.supportedApplications.map((appKey, i) => (
                <li key={i}>{advancedMsg(appKey)}</li>
              ))}
            </ul>
          )}
        </li>

        <li>
          {isManual ? (
            <>
              <div>{msg("loginTotpManualStep2")}</div>
              <code className="asunset-totp-secret">{totp.totpSecret}</code>
              <div>
                <a href={totp.qrUrl} className="asunset-link">
                  {msg("loginTotpScanBarcode")}
                </a>
              </div>
            </>
          ) : (
            <>
              <div>{msg("loginTotpStep2")}</div>
              <img
                src={`data:image/png;base64, ${totp.totpSecretQrCode}`}
                alt="TOTP QR code"
                className="asunset-totp-qr"
              />
              <div>
                <a href={totp.manualUrl} className="asunset-link">
                  {msg("loginTotpUnableToScan")}
                </a>
              </div>
            </>
          )}
        </li>

        <li>{msg("loginTotpStep3")}</li>
      </ol>

      <form action={url.loginAction} method="post" onSubmit={onSubmit}>
        <input type="hidden" name="totpSecret" value={totp.totpSecret} />
        {mode && <input type="hidden" name="mode" value={mode} />}

        <div className="asunset-field">
          <label htmlFor="totp" className="asunset-label">
            {msg("authenticatorCode")}
          </label>
          <OTPInput
            id="totp"
            name="totp"
            maxLength={6}
            value={code}
            onChange={setCode}
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
                  __html: messagesPerField.getFirstError("totp"),
                }}
              />
            </div>
          )}
        </div>

        <div className="asunset-field">
          <label htmlFor="userLabel" className="asunset-label">
            {msg("loginTotpDeviceName")}
            {labelRequired && (
              <span style={{ color: "var(--asunset-destructive)" }}> *</span>
            )}
          </label>
          <input
            id="userLabel"
            className="asunset-input"
            type="text"
            name="userLabel"
            autoComplete="off"
            aria-invalid={messagesPerField.existsError("userLabel")}
          />
          {messagesPerField.existsError("userLabel") && (
            <div
              className="asunset-alert asunset-alert--error"
              style={{ marginTop: "0.5rem" }}
            >
              <span
                dangerouslySetInnerHTML={{
                  __html: messagesPerField.getFirstError("userLabel"),
                }}
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          className="asunset-button"
          name="submitAction"
          value="Save"
          disabled={code.length < 6 || submitting}
        >
          {msgStr("doSubmit")}
        </button>

        {isAppInitiatedAction && (
          <button
            type="submit"
            className="asunset-button asunset-button--ghost"
            name="submitAction"
            value="Cancel"
          >
            {msgStr("doCancel")}
          </button>
        )}
      </form>
    </Template>
  );
}
