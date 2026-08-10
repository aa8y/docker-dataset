# syntax=docker/dockerfile:1
#
# Three-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the DuckDB counterpart of ../sqlite/Dockerfile. DuckDB is embedded --
# a database is just a file -- so, exactly as with SQLite, there is no server
# to boot and no init scripts to run at start: the build *builds the database
# file* (Extract -> Transform -> Load) and the final stage simply ships it.
#
# Engine note, and why this build has three stages where SQLite's has two. The
# official duckdb/duckdb image (multi-arch amd64 + arm64) is distroless
# (gcr.io/distroless/cc-debian12): a glibc-linked /duckdb binary and nothing
# else -- no shell, no package manager. That rules out both neighbours for the
# LOAD step: the Alpine builder that extracts and transforms the sources is
# musl-based and cannot run the glibc /duckdb binary, and the distroless final
# image has no shell to drive it. So a middle glibc stage
# (debian:bookworm-slim, the same Debian the distroless base is cut from)
# borrows /duckdb from the official image, builds the database file, and hands
# /data to the final stage.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# A dataset is described either by a text SQL source (SQL_FILES, fed to the
# duckdb CLI to build the database) or by a prebuilt DuckDB database file
# (DB_FILE, shipped as-is). Datasets with bespoke logic plug into the ETL steps
# without editing this file, via the convention-located
# scripts/<dataset>/{extract,transform,load} hooks.
#
# Data Sources.
# Chinook: https://github.com/lerocha/chinook-database (vendor-specific
#          Chinook_Sqlite.sql release asset; the scripts/chinook transform
#          hook rewrites its two SQLite-isms -- bracket-quoted identifiers and
#          forward-referencing FOREIGN KEYs -- into DuckDB SQL).

# Single version pin for the engine: the loader below borrows the /duckdb
# binary from this stage and the final image *is* this stage, so both always
# carry the same DuckDB release.
FROM duckdb/duckdb:1.5.5 AS engine

# ---------------------------------------------------------------------------
# Builder: extract, transform.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. a .sql script or a prebuilt .duckdb).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) of text SQL files
# fed to the duckdb CLI to build the database. Consumed by the loader stage
# below; declared here too so extract/transform hooks can key on it (the
# scripts/chinook hook rewrites each $SQL_FILES file in place). Mutually
# exclusive with DB_FILE.
ARG SQL_FILES
# Path (relative to the build dir) of a prebuilt DuckDB database file to ship
# as-is. Mutually exclusive with SQL_FILES.
ARG DB_FILE
# apk packages beyond the shared set. Builder-only: hooks that run here
# (extract, transform) can rely on them, the loader's load hook cannot.
ARG EXTRA_PREREQS

WORKDIR /tmp/build
# Per-dataset ETL hooks, located by convention as scripts/<dataset>/<step>
# (extract|transform|load) and executed at the matching stage below if present.
# Hooks are extensionless and run via their shebang, so a hook may be written in
# any language whose interpreter is in the executing stage (bash always; others
# via EXTRA_PREREQS for extract/transform, which run here in the builder --
# load hooks run in the Debian loader stage below).
COPY scripts/ /usr/local/lib/scripts/

# Resilient download options shared by the extract step and any dataset extract
# hook (inherited via the environment). Upstreams return transient 5xx/429s
# under load; retry with backoff so a momentary hiccup doesn't fail the whole
# build. Builder-only, so it never leaks into the final image.
ENV WGET_OPTS="--tries=5 --waitretry=10 --timeout=30 --retry-connrefused --retry-on-host-error --retry-on-http-error=429,500,502,503,504"

# Upstream-content fingerprint, computed on the host from cheap source metadata
# by bin/dataset-checksum and passed in as a build arg. Referenced in the RUN
# below so a real upstream change busts this layer and cascades a rebuild
# through EXTRACT -> TRANSFORM -> LOAD, while an unchanged dataset reuses the
# registry cache. Builder-only, so it never leaks into the final image.
ARG DATASET_CHECKSUM=
RUN echo "dataset checksum: ${DATASET_CHECKSUM}"

# EXTRACT. Shared tools + per-dataset extras, then fetch by URL type and run an
# optional dataset extract hook.
RUN apk add --no-cache \
      bash \
      bzip2 \
      ca-certificates \
      git \
      unzip \
      wget \
      $EXTRA_PREREQS && \
    bash -c ' \
      set -e; \
      case "$EXTRACT_URL" in \
        *.git)    git clone "$EXTRACT_URL" ;; \
        *.tar.gz) wget $WGET_OPTS -qO- "$EXTRACT_URL" | tar -xzf - ;; \
        *)        for u in $EXTRACT_URL; do wget $WGET_OPTS -q "$u"; done ;; \
      esac; \
      h="/usr/local/lib/scripts/${DATASET}/extract"; if [ -f "$h" ]; then "$h"; fi'

# TRANSFORM. Optional per-dataset transform hook.
RUN bash -c ' \
      set -e; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Loader: build the database file with the duckdb CLI (glibc stage).
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS loader

ARG DATASET
# Re-declared from the builder (see the comments there): the loader is the
# stage that actually consumes them.
ARG SQL_FILES
ARG DB_FILE

# The engine CLI, borrowed from the pinned official image the final stage is
# built from -- same binary, same version, no package install.
COPY --from=engine /duckdb /usr/local/bin/duckdb
# The extracted/transformed sources and the hook library, carried over from
# the builder so LOAD (and any load hook) sees the same build dir the earlier
# steps produced.
COPY --from=builder /usr/local/lib/scripts/ /usr/local/lib/scripts/
COPY --from=builder /tmp/build /tmp/build
WORKDIR /tmp/build

# LOAD. Build the database file at /data/${DATASET}.duckdb -- either by feeding
# the text SQL_FILES to the duckdb CLI, or by shipping a prebuilt DB_FILE
# as-is -- then run an optional dataset load hook and point the fixed-name
# /data/db.duckdb symlink at the result. The symlink exists because the final
# image is distroless: with no shell, its CMD must be exec-form with a fixed
# path (no ${DATASET} expansion at runtime), so every dataset image aims the
# same well-known name at its database file and they all share one CMD.
RUN bash -c ' \
      set -e; \
      mkdir -p /data; \
      DB="/data/${DATASET}.duckdb"; \
      if [ -n "$SQL_FILES" ]; then \
        for f in $SQL_FILES; do cat "$f"; echo; done | duckdb "$DB"; \
      elif [ -n "$DB_FILE" ]; then \
        cp "$DB_FILE" "$DB"; \
      else \
        echo "error: set either SQL_FILES (text SQL) or DB_FILE (prebuilt db)" >&2; exit 1; \
      fi; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi; \
      ln -s "${DATASET}.duckdb" /data/db.duckdb'

# ---------------------------------------------------------------------------
# Final image: the distroless official DuckDB CLI + the database file only.
# ---------------------------------------------------------------------------
FROM engine

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="DuckDB databases pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/duckdb-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/duckdb-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# Not consumed by the CMD (distroless: the CMD below must be exec-form with a
# fixed path, hence the db.duckdb symlink) -- recorded so `docker inspect`
# shows which dataset an image carries, matching the other engines.
ENV DATASET=${DATASET}

COPY --from=loader /data /data
WORKDIR /data

# Open the shipped database in the duckdb shell, via the fixed-path symlink the
# loader left (see the LOAD comment). The base image has no ENTRYPOINT and no
# shell, so this exec-form CMD is the container's whole process -- run with
# `-it` for an interactive session, or override with your own arguments (e.g.
# `... /duckdb -readonly -csv -c "SELECT 1" /data/<dataset>.duckdb`).
CMD ["/duckdb", "/data/db.duckdb"]
