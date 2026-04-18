import { useState, type FormEventHandler } from "react";
import { clsx } from "keycloakify/tools/clsx";
import type { PageProps } from "keycloakify/login/pages/PageProps";
import type { KcContext } from "../KcContext";
import type { I18n } from "../i18n";

export default function Login(
  props: PageProps<Extract<KcContext, { pageId: "login.ftl" }>, I18n>,
) {
  const { kcContext, i18n, Template, classes, doUseDefaultCss } = props;
  const {
    social,
    realm,
    url,
    usernameHidden,
    login,
    auth,
    registrationDisabled,
    messagesPerField,
  } = kcContext;
  const { msg, msgStr } = i18n;

  const [isLoginButtonDisabled, setIsLoginButtonDisabled] = useState(false);

  const onSubmit: FormEventHandler<HTMLFormElement> = (e) => {
    e.preventDefault();
    setIsLoginButtonDisabled(true);
    (e.target as HTMLFormElement).submit();
  };

  return (
    <Template
      kcContext={kcContext}
      i18n={i18n}
      doUseDefaultCss={doUseDefaultCss}
      classes={classes}
      displayMessage={!messagesPerField.existsError("username", "password")}
      headerNode={msg("loginAccountTitle")}
      displayInfo={
        realm.password && realm.registrationAllowed && !registrationDisabled
      }
      infoNode={
        <div>
          {msg("noAccount")}{" "}
          <a tabIndex={6} href={url.registrationUrl} className="asunset-link">
            {msg("doRegister")}
          </a>
        </div>
      }
      socialProvidersNode={
        realm.password && social?.providers !== undefined && social.providers.length !== 0 ? (
          <div className="asunset-providers">
            <div className="asunset-providers__title">
              {msg("identity-provider-login-label")}
            </div>
            {social.providers.map((p) => (
              <a
                key={p.alias}
                href={p.loginUrl}
                className="asunset-provider"
              >
                {p.iconClasses && <i className={clsx(p.iconClasses)} />}
                <span dangerouslySetInnerHTML={{ __html: p.displayName }} />
              </a>
            ))}
          </div>
        ) : null
      }
    >
      <div id="kc-form">
        <div id="kc-form-wrapper">
          {realm.password && (
            <form
              id="kc-form-login"
              onSubmit={onSubmit}
              action={url.loginAction}
              method="post"
            >
              {!usernameHidden && (
                <div className="asunset-field">
                  <label htmlFor="username" className="asunset-label">
                    {!realm.loginWithEmailAllowed
                      ? msg("username")
                      : !realm.registrationEmailAsUsername
                        ? msg("usernameOrEmail")
                        : msg("email")}
                  </label>
                  <input
                    tabIndex={2}
                    id="username"
                    className="asunset-input"
                    name="username"
                    defaultValue={login.username ?? ""}
                    type="text"
                    autoFocus
                    autoComplete="username"
                    aria-invalid={messagesPerField.existsError(
                      "username",
                      "password",
                    )}
                  />
                  {messagesPerField.existsError("username", "password") && (
                    <div className="asunset-alert asunset-alert--error" style={{ marginTop: "0.5rem" }}>
                      <span
                        dangerouslySetInnerHTML={{
                          __html: messagesPerField.getFirstError(
                            "username",
                            "password",
                          ),
                        }}
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="asunset-field">
                <label htmlFor="password" className="asunset-label">
                  {msg("password")}
                </label>
                <input
                  tabIndex={3}
                  id="password"
                  className="asunset-input"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={messagesPerField.existsError(
                    "username",
                    "password",
                  )}
                />
              </div>

              <div className="asunset-row">
                {realm.rememberMe && !usernameHidden && (
                  <label className="asunset-checkbox">
                    <input
                      tabIndex={5}
                      id="rememberMe"
                      name="rememberMe"
                      type="checkbox"
                      defaultChecked={!!login.rememberMe}
                    />
                    {msg("rememberMe")}
                  </label>
                )}
                {realm.resetPasswordAllowed && (
                  <a tabIndex={6} href={url.loginResetCredentialsUrl} className="asunset-link">
                    {msg("doForgotPassword")}
                  </a>
                )}
              </div>

              <input
                type="hidden"
                id="id-hidden-input"
                name="credentialId"
                value={auth?.selectedCredential ?? ""}
              />
              <button
                tabIndex={7}
                disabled={isLoginButtonDisabled}
                className="asunset-button"
                name="login"
                id="kc-login"
                type="submit"
              >
                {msgStr("doLogIn")}
              </button>
            </form>
          )}
        </div>
      </div>
    </Template>
  );
}
