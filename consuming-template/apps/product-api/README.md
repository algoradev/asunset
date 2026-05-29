# product-api

Minimal example product built on asunset. Swap the `Report` resource for
your actual domain.

For the full extension-point walkthrough (models, FGA, router, alembic,
compose overlay) see the top-level `consuming-template/README.md`. This
file covers one thing that bites every consumer: **how to onboard users
correctly without reinventing the membership plumbing.**

## Onboarding users

Don't write to `org_member` / Keycloak / OpenFGA directly — the
dual-write ordering and failure model are subtle (see
`asunset_core.auth.authorizer`). Use the platform membership endpoints.
There are three, and picking the right one is the whole game:

**Give a person (by email) access to the org** —
`POST /orgs/current/invites`. Creates the Keycloak user if needed,
adds membership + FGA tuples, and **always bootstraps a fresh
credential** (magic link or temp password per `INVITE_DELIVERY`).
Re-inviting an existing member re-issues credentials — Invite means
"issue access," full stop.

**Add an existing, already-onboarded user without resetting their
password** — `POST /orgs/current/members`. Membership + FGA tuples
only. No credential touch, no mail; the user keeps their current
password.

**Re-issue a credential to someone still pending** —
`POST /orgs/current/invites/{user_id}/resend`. Re-runs the credential
bootstrap for a pending member.

## Invariants worth internalizing

These are enforced by asunset, but your UI and any automation you build
(bulk import, SSO provisioning, etc.) should respect them rather than
work around them:

- **Invite is idempotent and always re-bootstraps.** Retrying
  a partially-failed invite is safe — orphan FGA tuples from a
  prior attempt are tolerated. There is no "add to org but send a
  notification instead of credentials" middle path; that ambiguity
  caused real confusion in production and was removed.
- **`temp_password` mode emails the recipient.** When
  `INVITE_DELIVERY=temp_password`, the new member gets a welcome mail
  with their temporary password (via the app-side Notifier, so it
  works even where outbound SMTP is blocked). The admin still sees the
  password in the API response as a backup. This needs the notifier
  configured (`NOTIFIER_BACKEND=resend` + `RESEND_API_KEY`); with the
  default `log` backend the mail only hits stdout.
- **`pending` means "unfinished credential bootstrap"** — derived from
  the Keycloak user's `requiredActions` (`UPDATE_PASSWORD` /
  `VERIFY_EMAIL`), *not* `emailVerified`. It clears for both
  magic-link and temp-password flows once the user finishes. Don't
  re-invite a user just to clear a stale badge — that re-issues
  credentials they may not need.
- **Removal is lockout-guarded.** `DELETE /orgs/current/members/{user_id}`
  refuses self-removal (400) and refuses removing the last admin
  (409). Both paths brick the org; the guards exist on purpose.
