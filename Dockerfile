# Deploy image for the Proa app — adapted from Proa's Railway guide
# (https://proa.so/docs/framework/railway). Railway builds this file,
# injects PORT, health-checks /readyz, then routes traffic.
#
# Note: the guide's BuildKit cache mounts need a real Railway service id
# in their cache keys (s/<service-id>-...), so they are omitted here.
# First deploys build from scratch (slow); add the mounts afterwards
# with the id from `railway status --json` to speed up rebuilds.

FROM rust:1.93-bookworm AS build

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git jq \
    && rm -rf /var/lib/apt/lists/*

COPY proa.lock.json /tmp/proa.lock.json

RUN proa_version="$(jq -er '.scaffold.cliVersion' /tmp/proa.lock.json)" \
    && cargo install proa-cli --version "=$proa_version" --locked

# Install the checksum-verified standalone Tailwind CLI.
RUN curl --proto '=https' --tlsv1.2 -fsSL https://proa.so/install.sh \
    | sh -s -- --tailwind-only --to /usr/local/bin --no-modify-path --yes

COPY . .

RUN proa build --locked --artifact-out /app/tarkov-map-app-bin

FROM debian:bookworm-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/tarkov-map-app-bin /usr/local/bin/tarkov-map-app
COPY --from=build /app/public ./public

ENV PROA_HOST=::
ENV RUST_LOG=info

CMD ["tarkov-map-app"]
