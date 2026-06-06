# Frontend React/Vite para Railway — build estático servido por nginx.
# Multi-stage: (1) compila con Node, (2) sirve /dist con nginx en $PORT.

# ---- build ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# --include=dev por si Railway fija NODE_ENV=production (necesitamos vite/tsc)
RUN npm install --include=dev --no-fund --no-audit
COPY . .
# VITE_API_URL se hornea en build; si no hay .env, api.ts cae a la URL de prod.
RUN npm run build

# ---- serve ----
FROM nginx:alpine
# La imagen oficial hace envsubst de /etc/nginx/templates/*.template al arrancar,
# sustituyendo ${PORT}. Railway inyecta PORT; 8080 es el fallback local.
ENV PORT=8080
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
