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
# Per-dataset sources/prereqs are declared in manifest.yml and arrive as the
# ARGs below. Only the handful of datasets with irreducibly bespoke fetch /
# reformat logic (omdb, adventureworks, sportsdb) need a `case "$DATASET"`
# branch; the plain pgFoundry datasets are fully described by EXTRACT_URL +
# SQL_FILES.
#
# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   https://github.com/yugabyte/yugabyte-db/tree/master/sample
#             (Yugabyte's mirror of the original SportsDB sample; the
#             upstream www.sportsdb.org download is no longer available.)
#             Yugabyte's dump creates every index with its own `USING lsm`
#             access method, which vanilla Postgres lacks and which aborts
#             init; we rewrite `USING lsm` -> `USING btree` (Postgres' default
#             ordered index, the semantic equivalent) before loading.
# OMDB:       https://github.com/df7cb/omdb-postgresql
#             (CSV data is fetched from www.omdb.org at build time and
#             shipped alongside the init script so psql \copy resolves it.)
# AdventureWorks:
#             https://github.com/lorint/AdventureWorks-for-Postgres
#             (CSVs come from Microsoft's AdventureWorks 2014 OLTP zip,
#             reformatted via the upstream Ruby script, and shipped next
#             to the init script.)

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

WORKDIR /tmp/build
COPY preprocess-adventureworks.rb /usr/local/lib/preprocess-adventureworks.rb

# EXTRACT. Shared tools + per-dataset extras, then fetch by URL type and run
# any dataset-specific fetch (omdb's CSV download, AdventureWorks' MS zip).
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
      case "$DATASET" in \
        omdb) \
          (cd omdb-postgresql && ./download) ;; \
        adventureworks) \
          (cd AdventureWorks-for-Postgres && \
            wget -q -O ms.zip https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks-oltp-install-script.zip && \
            unzip -q -o ms.zip && \
            rm ms.zip) ;; \
      esac'

# TRANSFORM. Only the datasets whose raw sources need reformatting before load.
RUN bash -c ' \
      set -e; \
      case "$DATASET" in \
        sportsdb) \
          sed -i "s/USING lsm/USING btree/g" sportsdb_*.sql ;; \
        omdb) \
          bunzip2 --force omdb-postgresql/www.omdb.org/data/*.bz2 ;; \
        adventureworks) \
          (cd AdventureWorks-for-Postgres && ruby /usr/local/lib/preprocess-adventureworks.rb) ;; \
      esac'

# LOAD. Assemble the per-dataset init script and ship any CSV data dirs so the
# dump's \copy directives resolve at container start.
RUN bash -c ' \
      set -e; \
      mkdir -p /docker-entrypoint-initdb.d; \
      INIT="/docker-entrypoint-initdb.d/${DATASET}.sql"; \
      echo "CREATE DATABASE ${DATASET};" >> "$INIT"; \
      echo "\c ${DATASET};" >> "$INIT"; \
      [ -n "$DB_EXTENSION" ] && echo "CREATE EXTENSION IF NOT EXISTS ${DB_EXTENSION};" >> "$INIT"; \
      [ -n "$CD_DIR" ] && echo "\cd ${CD_DIR}" >> "$INIT"; \
      for f in $SQL_FILES; do cat "$f" >> "$INIT"; done; \
      case "$DATASET" in \
        omdb) \
          mkdir -p /docker-entrypoint-initdb.d/www.omdb.org && \
          mv omdb-postgresql/www.omdb.org/data /docker-entrypoint-initdb.d/www.omdb.org/data ;; \
        adventureworks) \
          mkdir -p /docker-entrypoint-initdb.d/adventureworks && \
          mv AdventureWorks-for-Postgres/*.csv /docker-entrypoint-initdb.d/adventureworks/ ;; \
      esac'

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
