# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the CockroachDB counterpart of ../postgres/Dockerfile and keeps the
# same shape: the builder stage runs Extract -> Transform -> Load as three
# distinct RUN steps driven entirely by build args from manifest.yml, and the
# final stage COPYs the assembled init artifacts onto the official CockroachDB
# image. Build tools live only in the builder, so the final image never carries
# them.
#
# Engine note. CockroachDB is PostgreSQL wire- and (largely) SQL-compatible, so
# the dataset pattern carries over from postgres almost unchanged. The official
# `cockroachdb/cockroach` image's entrypoint (cockroach.sh) honours the same
# /docker-entrypoint-initdb.d/*.sql convention the official postgres image uses
# *when the container is started with `start-single-node`*: it brings up a
# single node, creates the database named by COCKROACH_DATABASE, then runs every
# init script against that database. So unlike postgres we do NOT emit a
# `CREATE DATABASE` + `\c` header -- COCKROACH_DATABASE (set per dataset below)
# creates the database and the scripts already run inside it.
#
# There is no official Alpine image for CockroachDB (the official image is
# UBI-minimal). It is still slim (~170 MB) and multi-arch (amd64 + arm64), so it
# satisfies the "thin" goal while keeping the upstream-supported init flow.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# Most datasets are fully described by EXTRACT_URL + SQL_FILES. Datasets with
# bespoke logic plug into the ETL steps without editing this file, via the
# convention-located scripts/<dataset>/{extract,transform,load} hooks (run at
# the matching stage if present, keyed on $DATASET).
#
# Data Sources.
# Chinook:   https://github.com/yugabyte/yugabyte-db/tree/master/sample
#            (PostgreSQL-dialect Chinook digital-media store; quoted CamelCase
#            identifiers, plain DDL + INSERT data.)
# Northwind: https://github.com/yugabyte/yugabyte-db/tree/master/sample
#            (PostgreSQL-dialect Northwind sample; plain DDL + INSERT data.)

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. the chinook/northwind .sql dump set).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) cat'd into the
# init script after extract/transform.
ARG SQL_FILES
# apk packages beyond the shared set.
ARG EXTRA_PREREQS
# Optional: target access method for `USING lsm` index DDL. Defaults to "lsm"
# (a no-op); set to "gin"/"btree"/etc. to rewrite Yugabyte's lsm indexes.
ARG INDEX_METHOD=lsm

WORKDIR /tmp/build
# Per-dataset ETL hooks, located by convention as scripts/<dataset>/<step>
# (extract|transform|load) and executed at the matching stage below if present.
# Hooks are extensionless and run via their shebang, so a hook may be written in
# any language whose interpreter is in the builder (bash always; others via
# EXTRA_PREREQS).
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

# TRANSFORM. Optional index-method rewrite (a no-op unless INDEX_METHOD is set)
# plus an optional dataset transform hook.
RUN bash -c ' \
      set -e; \
      if [ "$INDEX_METHOD" != "lsm" ]; then sed -i "s/USING lsm/USING ${INDEX_METHOD}/g" *.sql; fi; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the per-dataset init script by concatenating the SQL files.
# No CREATE DATABASE / connect header: the official entrypoint creates the
# COCKROACH_DATABASE database (set per dataset in the final stage) and runs
# every init script against it. An optional dataset load hook can ship extra
# data dirs the dump references.
RUN bash -c ' \
      set -e; \
      mkdir -p /docker-entrypoint-initdb.d; \
      INIT="/docker-entrypoint-initdb.d/${DATASET}.sql"; \
      for f in $SQL_FILES; do cat "$f" >> "$INIT"; echo >> "$INIT"; done; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Final image: official CockroachDB + the assembled init artifacts only.
# ---------------------------------------------------------------------------
FROM cockroachdb/cockroach:v25.4.11

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="CockroachDB images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/cockroach-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/cockroach-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# Names the database the entrypoint creates and runs the init scripts against.
# The cockroach.sh entrypoint only honours this (and /docker-entrypoint-initdb.d)
# when the container is started with `start-single-node`, which the CMD does.
ENV COCKROACH_DATABASE=${DATASET}

COPY --from=builder /docker-entrypoint-initdb.d /docker-entrypoint-initdb.d

# Single-node cluster in insecure mode -- these are throwaway practice/test
# images (mirroring the trivial credentials the postgres/mysql images use), and
# insecure mode gives the simplest connection: `cockroach sql --insecure`. The
# entrypoint still runs the init scripts under /docker-entrypoint-initdb.d on
# first boot, after the COCKROACH_DATABASE database is created.
CMD ["start-single-node", "--insecure"]
