# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# The builder stage runs Extract -> Transform -> Load as three distinct RUN
# steps, driven entirely by build args whose values come from manifest.yml.
# Build tools live only here, so the final image never carries them and there
# is nothing to purge. The final stage simply COPYs the assembled init
# artifacts onto the official postgres image.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# Plain pgFoundry datasets are fully described by EXTRACT_URL + SQL_FILES. The
# few datasets with bespoke logic plug into the ETL steps without editing this
# file, via two generic mechanisms:
#   * INDEX_METHOD - rewrites `USING lsm` index DDL (defaults to a no-op);
#                    set per-dataset in manifest.yml (the Yugabyte sportsdb dump).
#   * scripts/<dataset>/{extract,transform,load}.sh - convention-located scripts
#                    run at the matching stage if present, keyed on $DATASET. No
#                    manifest wiring needed; just drop the file in (e.g. omdb's
#                    CSV download, AdventureWorks' data zip + CSV reformat).
#
# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   https://github.com/yugabyte/yugabyte-db/tree/master/sample
#             (Yugabyte's mirror of the original SportsDB sample; the
#             upstream www.sportsdb.org download is no longer available.)
#             Yugabyte's dump creates every index with its own `USING lsm`
#             access method, which vanilla Postgres lacks and which aborts
#             init; we rewrite it to `USING btree` (Postgres' default ordered
#             index, the semantic equivalent) via INDEX_METHOD before loading.
# OMDB:       https://github.com/df7cb/omdb-postgresql
#             (CSV data is fetched from www.omdb.org at build time and
#             shipped alongside the init script so psql \copy resolves it.)
# AdventureWorks:
#             https://github.com/lorint/AdventureWorks-for-Postgres
#             (CSVs come from Microsoft's AdventureWorks 2014 OLTP zip,
#             reformatted via a Ruby script, and shipped next to the init
#             script.)

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. the sportsdb .sql dump set).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) cat'd into the
# init script after extract/transform.
ARG SQL_FILES
# apk packages beyond the shared set (e.g. "ruby" for adventureworks).
ARG EXTRA_PREREQS
# Optional: emits `CREATE EXTENSION IF NOT EXISTS <name>;` into the init script.
ARG DB_EXTENSION
# Optional: emits `\cd <dir>` so the dump's relative \copy paths resolve when
# psql runs the init script at container start.
ARG CD_DIR
# Optional: target access method for `USING lsm` index DDL. Defaults to "lsm"
# (a no-op); set to "btree" to rewrite Yugabyte's lsm indexes for Postgres.
ARG INDEX_METHOD=lsm

WORKDIR /tmp/build
# Per-dataset ETL hooks, located by convention as scripts/<dataset>/<step>
# (extract|transform|load) and executed at the matching stage below if present.
# Hooks are extensionless and run via their shebang, so a hook may be written in
# any language whose interpreter is in the builder (bash always; others via
# EXTRA_PREREQS, e.g. ruby for adventureworks).
COPY scripts/ /usr/local/lib/scripts/

# EXTRACT. Shared tools + per-dataset extras, then fetch by URL type and run an
# optional dataset extract hook (e.g. omdb's CSV download, the AdventureWorks
# data zip).
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
        *.tar.gz) wget -qO- "$EXTRACT_URL" | tar -xzf - ;; \
        *)        for u in $EXTRACT_URL; do wget -q "$u"; done ;; \
      esac; \
      h="/usr/local/lib/scripts/${DATASET}/extract"; if [ -f "$h" ]; then "$h"; fi'

# TRANSFORM. Optional index-method rewrite (a no-op unless INDEX_METHOD is set)
# plus an optional dataset transform hook (e.g. AdventureWorks' CSV reformat).
RUN bash -c ' \
      set -e; \
      if [ "$INDEX_METHOD" != "lsm" ]; then sed -i "s/USING lsm/USING ${INDEX_METHOD}/g" *.sql; fi; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the per-dataset init script, then run an optional dataset load
# hook to ship CSV data dirs so the dump's \copy directives resolve at start.
RUN bash -c ' \
      set -e; \
      mkdir -p /docker-entrypoint-initdb.d; \
      INIT="/docker-entrypoint-initdb.d/${DATASET}.sql"; \
      echo "CREATE DATABASE ${DATASET};" >> "$INIT"; \
      echo "\c ${DATASET};" >> "$INIT"; \
      [ -n "$DB_EXTENSION" ] && echo "CREATE EXTENSION IF NOT EXISTS ${DB_EXTENSION};" >> "$INIT"; \
      [ -n "$CD_DIR" ] && echo "\cd ${CD_DIR}" >> "$INIT"; \
      for f in $SQL_FILES; do cat "$f" >> "$INIT"; done; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Final image: official postgres + the assembled init artifacts only.
# ---------------------------------------------------------------------------
FROM postgres:18-alpine

LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="PostgreSQL images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/postgres-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/postgres-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG PG_USER=postgres
ARG PG_HOME=/home/$PG_USER
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
# Don't override this value. Do not use this value for `POSTGRES_USER`. We're making this change to
# to make sure the default database created by the `postgres` base image does not interfere with
# our database creation while populating data.
ENV POSTGRES_DB=donotuse

# Enable psql history.
RUN mkdir -p $PG_HOME && \
    touch $PG_HOME/.psql_history && \
    chown -R $PG_USER:$PG_USER $PG_HOME

COPY --from=builder /docker-entrypoint-initdb.d /docker-entrypoint-initdb.d

USER $PG_USER
WORKDIR $PG_HOME
