# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the MySQL counterpart of ../postgres/Dockerfile and keeps the same
# shape: the builder stage runs Extract -> Transform -> Load as three distinct
# RUN steps driven entirely by build args from manifest.yml, and the final
# stage COPYs the assembled init artifacts onto a thin database image. Build
# tools live only in the builder, so the final image never carries them.
#
# Engine note. There is no official Alpine image for Oracle MySQL (the official
# `mysql` image is Oracle Linux / Debian based, and Alpine's own repositories
# ship MariaDB in place of MySQL). To honour the "thin, Alpine-based" goal we
# build on the community `yobasystems/alpine-mariadb` image: MariaDB is the
# MySQL drop-in Alpine itself substitutes, and that image's entrypoint honours
# the same MYSQL_* env vars and /docker-entrypoint-initdb.d/*.sql convention the
# official postgres image uses, so the dataset pattern carries over unchanged.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# Most datasets are fully described by EXTRACT_URL + SQL_FILES. Datasets with
# bespoke logic plug into the ETL steps without editing this file, via the
# convention-located scripts/<dataset>/{extract,transform,load} hooks (run at
# the matching stage if present, keyed on $DATASET; e.g. moma's CSV staging).
#
# Because each image carries exactly one dataset, the transform step strips any
# database-level DDL (CREATE/DROP DATABASE|SCHEMA, USE) the upstream dump ships
# so every dataset loads into the single ${DATASET} database the load step
# creates -- the MySQL analogue of the postgres `CREATE DATABASE` + `\c` header.
#
# Data Sources.
# Sakila:    https://dev.mysql.com/doc/index-other.html (MySQL's own sample;
#            the original of the Sakila/"DVD store" model that pagila ports to
#            Postgres).
# World:     https://dev.mysql.com/doc/index-other.html (MySQL's canonical world
#            sample: city, country, countrylanguage).
# Chinook:   https://github.com/lerocha/chinook-database (vendor-specific
#            Chinook_MySql.sql release asset).
# Northwind: https://github.com/dalers/mywind (MySQL port of the Microsoft
#            Access Northwind sample).

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually.
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) cat'd into the
# init script after extract/transform.
ARG SQL_FILES
# apk packages beyond the shared set.
ARG EXTRA_PREREQS

WORKDIR /tmp/build
# Per-dataset ETL hooks, located by convention as scripts/<dataset>/<step>
# (extract|transform|load) and executed at the matching stage below if present.
# Hooks are extensionless and run via their shebang, so a hook may be written in
# any language whose interpreter is in the builder (bash always; others via
# EXTRA_PREREQS).
COPY scripts/ /usr/local/lib/scripts/

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
        *.tar.gz) wget -qO- "$EXTRACT_URL" | tar -xzf - ;; \
        *)        for u in $EXTRACT_URL; do wget -q "$u"; done ;; \
      esac; \
      h="/usr/local/lib/scripts/${DATASET}/extract"; if [ -f "$h" ]; then "$h"; fi'

# TRANSFORM. Strip the upstream dump'\''s database-level DDL so the data lands in
# the single ${DATASET} database the load step creates, then run an optional
# dataset transform hook.
RUN bash -c ' \
      set -e; \
      for f in $SQL_FILES; do \
        [ -f "$f" ] || continue; \
        grep -ivE "^[[:space:]]*((/\*![0-9]+[[:space:]]+)?(CREATE|DROP)[[:space:]]+(DATABASE|SCHEMA)|USE[[:space:]])" "$f" > "$f.tmp"; \
        mv "$f.tmp" "$f"; \
      done; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the per-dataset init script (create + use the dataset database,
# then concatenate the SQL files), then run an optional dataset load hook to
# ship any data dirs the dump references.
RUN bash -c ' \
      set -e; \
      mkdir -p /docker-entrypoint-initdb.d; \
      INIT="/docker-entrypoint-initdb.d/${DATASET}.sql"; \
      printf "CREATE DATABASE IF NOT EXISTS \`%s\`;\nUSE \`%s\`;\n" "$DATASET" "$DATASET" >> "$INIT"; \
      for f in $SQL_FILES; do cat "$f" >> "$INIT"; echo >> "$INIT"; done; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Final image: thin Alpine MariaDB + the assembled init artifacts only.
# ---------------------------------------------------------------------------
FROM yobasystems/alpine-mariadb:11.4.9

LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="MySQL (MariaDB) images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/mysql-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/mysql-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# A known root password so tests (and users) can connect without scraping the
# random password the entrypoint would otherwise generate. MYSQL_DATABASE must
# be non-empty for the entrypoint to process /docker-entrypoint-initdb.d, and
# names the database the init script loads into.
ENV MYSQL_ROOT_PASSWORD=mysql
ENV MYSQL_DATABASE=${DATASET}

COPY --from=builder /docker-entrypoint-initdb.d /docker-entrypoint-initdb.d
