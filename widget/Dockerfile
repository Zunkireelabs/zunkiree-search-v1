# Stage 1: Build
# No VITE_* build-time vars needed — widget/src reads its config (data-site-id,
# data-api-url) from the embedding <script> tag at runtime, not from
# import.meta.env. Verified 2026-09-17: no `import.meta.env` usage anywhere
# in widget/src.
FROM node:24-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
