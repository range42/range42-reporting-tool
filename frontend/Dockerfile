FROM node:24-bookworm-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM busybox:stable AS dist
WORKDIR /srv
COPY --from=build /app/dist ./
# 'dist' stage is consumed by the deploy step to populate the frontend_dist volume.
