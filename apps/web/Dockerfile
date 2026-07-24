# Multi-stage: `dev` runs vite's dev server; `prod` builds static assets
# and serves them via nginx. Select the stage with docker-compose target.

# ---------- base (deps) ----------
FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund

# ---------- dev ----------
FROM node:20-alpine AS dev

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---------- build ----------
FROM node:20-alpine AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG VITE_API_URL
ARG VITE_KEYCLOAK_URL
ARG VITE_KEYCLOAK_REALM
ARG VITE_KEYCLOAK_CLIENT_ID
ARG VITE_BRAND_NAME
ARG VITE_RESOURCE_NAME
ARG VITE_RESOURCE_PLURAL
ARG VITE_RESOURCE_NEW_LABEL
ARG VITE_RESOURCE_EMPTY_LABEL
ARG VITE_RESOURCE_SHARE_DESC
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_KEYCLOAK_URL=${VITE_KEYCLOAK_URL} \
    VITE_KEYCLOAK_REALM=${VITE_KEYCLOAK_REALM} \
    VITE_KEYCLOAK_CLIENT_ID=${VITE_KEYCLOAK_CLIENT_ID} \
    VITE_BRAND_NAME=${VITE_BRAND_NAME} \
    VITE_RESOURCE_NAME=${VITE_RESOURCE_NAME} \
    VITE_RESOURCE_PLURAL=${VITE_RESOURCE_PLURAL} \
    VITE_RESOURCE_NEW_LABEL=${VITE_RESOURCE_NEW_LABEL} \
    VITE_RESOURCE_EMPTY_LABEL=${VITE_RESOURCE_EMPTY_LABEL} \
    VITE_RESOURCE_SHARE_DESC=${VITE_RESOURCE_SHARE_DESC}

RUN npm run build

# ---------- prod ----------
FROM nginx:1.27-alpine AS prod

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
