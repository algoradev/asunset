# Builds the Keycloakify theme JAR, leaves it on a shared volume for
# the Keycloak container to load from /opt/keycloak/providers/.
# Targets Keycloak 25 — the "for-kc-22-to-25" JAR is the right one.

FROM node:20-alpine AS builder

# Keycloakify shells out to Maven to package the final JAR. Alpine's maven
# pulls in openjdk17 as a dep.
RUN apk add --no-cache maven zip unzip

WORKDIR /app

COPY package.json ./
RUN npm install --no-audit --no-fund
# postinstall calls `keycloakify update-kc-gen`; if that failed silently,
# the committed stub at src/kc.gen.tsx is a safe fallback for tsc.

COPY tsconfig.json tsconfig.node.json vite.config.ts index.html ./
COPY src ./src

RUN npm run build-keycloak-theme \
  && ls -la dist_keycloak

# ---- distribution stage ----
FROM alpine:3.19

WORKDIR /theme
COPY --from=builder /app/dist_keycloak/*.jar ./

# Copy JARs into the shared providers volume. One-shot service: exits 0
# when done so compose `service_completed_successfully` unblocks Keycloak.
CMD ["sh", "-c", "set -e; mkdir -p /out; cp -v /theme/*.jar /out/; echo 'theme installed'"]
