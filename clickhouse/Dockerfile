# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the ClickHouse counterpart of ../postgres/Dockerfile and keeps the
# same shape: the builder stage runs Extract -> Transform -> Load as three
# distinct RUN steps driven entirely by build args from manifest.yml, and the
# final stage COPYs the assembled init artifacts onto the official ClickHouse
# image. Build tools live only in the builder, so the final image never carries
# them.
#
# Engine note. ClickHouse is a columnar OLAP engine, so it is the first engine
# here whose *data model* -- not just its SQL spelling -- differs from the
# PostgreSQL sample dumps: a table's storage engine (`MergeTree` for all of
# these) and its sorting key are part of its definition, columns are NOT NULL
# unless declared Nullable, and there are no constraints, sequences or ordinary
# secondary indexes. Translating a dump is therefore a real rewrite rather than
# a filter -- and one worth doing carefully, because the dialect is tolerant
# enough that the wrong answer is silent: 26.8 accepts most of a pgFoundry
# CREATE TABLE verbatim and then stores every NULL as a zero and every table
# with no sorting key. scripts/pgsql/transform does that rewrite; see its module
# docstring for the rule set and the error (or the silence) each rule avoids.
#
# Init model. The official `clickhouse/clickhouse-server` entrypoint follows the
# same /docker-entrypoint-initdb.d convention the postgres and mysql images use:
# on a first start with an empty data dir it brings up a temporary server bound
# to 127.0.0.1, creates the database named by CLICKHOUSE_DB, feeds every
# *.sql / *.sql.gz / *.sh file in that directory to `clickhouse-client
# --multiquery`, and only then restarts the real server on all interfaces. So,
# like the other server engines, these images ship an init script and load at
# first container start rather than baking a database file at build time
# (/var/lib/clickhouse is a VOLUME in the base image, so a baked data dir would
# be shadowed the moment the container ran).
#
# A dataset's init script is /docker-entrypoint-initdb.d/${DATASET}.sql. Any
# data files it reads (CSV, TSV, Parquet) ship next to it under
# /docker-entrypoint-initdb.d/${DATASET}/ and are read by the client at start
# via `INSERT ... FROM INFILE`; the entrypoint's file loop ignores that
# subdirectory (it matches none of its cases and just logs "ignoring"). Unlike
# the DuckDB images, those files are needed at *run* time, not only at build
# time, so they are part of the shipped image and the structure tests assert
# they are there.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# Most datasets are fully described by EXTRACT_URL + SQL_FILES. Datasets with
# bespoke logic plug into the ETL steps without editing this file, via the
# convention-located scripts/<dataset>/{extract,transform,load} hooks (run at
# the matching stage if present, keyed on $DATASET).
#
# Data Sources.
# PG Foundry:  http://pgfoundry.org/frs/?group_id=1000150
#              (world, iso3166, frenchtowns, usda, dellstore; PostgreSQL DDL +
#              COPY data, translated to ClickHouse by scripts/pgsql.)
# Chinook /    https://github.com/yugabyte/yugabyte-db/tree/master/sample
# PGExercises: (PostgreSQL-dialect mirrors, through the same scripts/pgsql hook;
#              chinook ships one INSERT per row, which that hook coalesces.)
# NYC TLC:     https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
#              (a pinned monthly Parquet file, shipped in the image and read at
#              start with `INSERT ... FROM INFILE ... FORMAT Parquet`.)
# StackExchange: https://archive.org/details/stackexchange
#              (per-table XML, converted to CREATE TABLE + batched INSERTs.)

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. the chinook .sql dump set, a .parquet).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) cat'd into the
# init script after extract/transform.
ARG SQL_FILES
# apk packages beyond the shared set (e.g. "python3" for the pgsql translator,
# "p7zip python3 py3-lxml" for the StackExchange dumps).
ARG EXTRA_PREREQS

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
# optional dataset extract hook (e.g. the StackExchange 7z unpack, geonames' zip).
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

# TRANSFORM. Optional per-dataset transform hook: the PostgreSQL-dump
# translator, the XML -> SQL emitters, or the small hooks that stage an
# in-repo schema and append its load statements.
RUN bash -c ' \
      set -e; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the per-dataset init script by concatenating the SQL files
# behind a two-line header. The entrypoint creates the CLICKHOUSE_DB database
# and then runs every init script through `clickhouse-client --multiquery` with
# no default database, so the header has to name it: `USE` sets the session
# database for the rest of the script, which is what lets every statement below
# stay unqualified (verified against the 26.8 entrypoint). CREATE DATABASE IF
# NOT EXISTS ahead of it is belt-and-braces -- the entrypoint has already
# created it -- so the script also works when replayed by hand against a
# running server. Both identifiers are backtick-quoted, ClickHouse's own
# identifier quoting, so a dataset name that collides with a keyword still
# parses. An optional dataset load hook ships the data files the script reads.
RUN bash -c ' \
      set -e; \
      mkdir -p /docker-entrypoint-initdb.d; \
      INIT="/docker-entrypoint-initdb.d/${DATASET}.sql"; \
      echo "CREATE DATABASE IF NOT EXISTS \`${DATASET}\`;" >> "$INIT"; \
      echo "USE \`${DATASET}\`;" >> "$INIT"; \
      for f in $SQL_FILES; do cat "$f" >> "$INIT"; echo >> "$INIT"; done; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Final image: official ClickHouse + the assembled init artifacts only.
# ---------------------------------------------------------------------------
# The Alpine flavour of the official image: multi-arch (amd64 + arm64) and the
# smallest official tag, which keeps these images in the same weight class as
# the other engines here. Pinned to a release on the current LTS line; bump
# deliberately, like any other upstream pin.
FROM clickhouse/clickhouse-server:26.8.2.7-alpine

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="ClickHouse images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/clickhouse-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/clickhouse-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# Names the database the entrypoint creates before it runs the init scripts.
# The entrypoint interpolates this straight into `CREATE DATABASE IF NOT EXISTS
# $CLICKHOUSE_DB` with no quoting, so every dataset name here is a bare
# ClickHouse identifier (which is why the nyc-taxi *tag* carries the dataset
# name `nyc_taxi`: a hyphen is not one).
ENV CLICKHOUSE_DB=${DATASET}
# Keep the base image's stock `default` user: no password and reachable from
# any address. Left to itself the entrypoint sees an unset CLICKHOUSE_PASSWORD
# and rewrites users.d to restrict `default` to 127.0.0.1, which would make
# these images the only ones here that cannot be reached over a published port.
# These are throwaway practice/test images -- the same reasoning behind the
# postgres/mysql images' trivial credentials and the cockroach images' insecure
# mode -- so the documented, supported opt-out is used instead of shipping a
# users.d override of our own.
ENV CLICKHOUSE_SKIP_USER_SETUP=1

# The init script plus, for datasets whose load statements read a file, the
# data files under /docker-entrypoint-initdb.d/${DATASET}/. Both are needed at
# container start, so unlike the build-time-only sources they ship in the image.
COPY --from=builder /docker-entrypoint-initdb.d /docker-entrypoint-initdb.d

# No CMD: the base image's entrypoint starts clickhouse-server when it is given
# no arguments, running the init scripts above on the first (empty-data-dir)
# start. Connect with `docker exec -it <container> clickhouse-client -d <db>`.
