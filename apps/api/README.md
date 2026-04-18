# asunset-api

FastAPI resource server for the asunset template.

Run via the root `docker compose` — this package is not meant to run standalone
outside the stack (it needs Keycloak, Postgres, and OpenFGA to start cleanly).

## Local dev

```sh
docker compose -f compose.yml -f compose.dev.yml up api
```

## Tests

```sh
docker compose run --rm api pytest
```
