# syntax=docker/dockerfile:1
#
# Three-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the Apache Druid counterpart of ../cockroach/Dockerfile: a builder
# stage runs Extract -> Transform -> Load as three distinct RUN steps driven
# entirely by build args from manifest.yml, and the final stage COPYs the
# assembled artifacts onto a runnable engine. Build tools live only in the
# builder, so the final image never carries them.
#
# Engine note, and why this image is built from the binary distribution rather
# than FROM apache/druid. Every published `apache/druid` tag is amd64-only (the
# upstream image builds the web console during its own build, which does not
# resolve on arm64 -- see the --platform=linux/amd64 pin in
# distribution/docker/Dockerfile upstream). This repo publishes every image for
# linux/amd64 *and* linux/arm64 on native runners, so the official image is not
# an option. The `engine` stage below therefore downloads the pinned Apache
# Druid binary release -- which is pure Java and architecture-independent --
# verifies it against the release's published SHA-512, trims it, and the final
# stage lays it on the multi-arch Eclipse Temurin JRE. The result runs services
# the same way the official image does (bin/run-java, the bundled
# conf/druid/single-server profiles, druid_* env -> Druid properties), so
# anything you know about `apache/druid` still applies.
#
# Engine note 2: why the Druid download is its own stage. The binary release is
# 625 MB, by far the most expensive thing this build fetches, and it has nothing
# to do with which dataset an image carries. Keeping it in a stage of its own --
# whose only inputs are the version pin and its checksum -- means a dataset
# change (a new tag, an edited hook, a refreshed upstream dump) never busts it;
# the registry build cache and the local layer cache both reuse it verbatim.
#
# Data model: init-at-start, like the repo's other server engines. Druid has no
# DDL + INSERT/COPY load path -- data enters through an *ingestion task* that
# writes immutable segments -- so the build cannot bake a loaded database into
# the image the way the DuckDB/SQLite builds do. Instead the build ships, per
# table, a CSV data file plus a native batch ingestion spec, and the entrypoint
# submits every spec on first boot and waits for the segments to load before
# announcing readiness. One table becomes one datasource of the same name, so
# `SELECT * FROM city` works exactly as it does on the relational engines.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# Datasets plug into the ETL steps via the convention-located
# scripts/<dataset>/{extract,transform,load} hooks (run at the matching stage if
# present, keyed on $DATASET).
#
# Data Sources.
# PG Foundry:  http://pgfoundry.org/frs/?group_id=1000150
#              (PostgreSQL dumps; the shared scripts/pgsql transform parses
#              their DDL and COPY/INSERT data into per-table CSV + specs.)
# GeoNames:    https://download.geonames.org/export/dump/
# OpenFlights: https://github.com/jpatokal/openflights/tree/master/data
# MoMA:        https://github.com/MuseumofModernArt/collection
#              (All three publish only delimited text, so their schema is
#              authored in-repo and their hooks assemble the PostgreSQL dump
#              upstream never shipped before handing it to scripts/pgsql --
#              see scripts/pgdump.py for why.)

# ---------------------------------------------------------------------------
# Engine: the pinned Apache Druid binary distribution, trimmed.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS engine

# Single version pin for the engine. Druid 37 officially supports Java 17 and
# 21; the final stage runs it on 21 (see there for why not 17).
ARG DRUID_VERSION=37.0.0
# SHA-512 of apache-druid-${DRUID_VERSION}-bin.tar.gz, taken from the release's
# published checksum at
# https://downloads.apache.org/druid/37.0.0/apache-druid-37.0.0-bin.tar.gz.sha512
# and pinned here rather than fetched at build time. Pinning is the stronger
# check of the two: a checksum downloaded next to the artifact only proves the
# mirror served a consistent pair, while a value committed to this repository
# proves the bytes are the ones this Dockerfile was written against. It is also
# one less network round-trip that can fail a build.
ARG DRUID_SHA512=ba2f23755676a057df93e6ceb5cc9d158d1b0c8f693a9b189d7048c57aea161773b039076bfeb5d2eb1bc1cd318d8f80a5030bcb6ab7deaf30ba8b019cfb57be

# dlcdn.apache.org is the ASF's CDN and carries only current releases; when a
# release ages out (or the CDN hiccups) archive.apache.org still has it. Both
# are tried before the build gives up, and the checksum above gates whichever
# one answered -- a truncated or substituted tarball fails here, not at runtime.
RUN apk add --no-cache ca-certificates tar wget && \
    for base in https://dlcdn.apache.org/druid https://archive.apache.org/dist/druid; do \
      wget --tries=5 --waitretry=10 --timeout=60 --retry-connrefused \
           --retry-on-host-error --retry-on-http-error=429,500,502,503,504 \
           -q -O /tmp/druid.tar.gz \
           "${base}/${DRUID_VERSION}/apache-druid-${DRUID_VERSION}-bin.tar.gz" && break; \
    done && \
    echo "${DRUID_SHA512}  /tmp/druid.tar.gz" | sha512sum -c - && \
    mkdir -p /opt && \
    tar -xzf /tmp/druid.tar.gz -C /opt && \
    mv "/opt/apache-druid-${DRUID_VERSION}" /opt/druid && \
    rm -f /tmp/druid.tar.gz

# Trim, in a RUN of its own so editing the keep-list never re-downloads the
# 625 MB tarball above.
#
# extensions/ is 474 MB of the 687 MB distribution and Druid loads only what
# druid.extensions.loadList names, so everything outside the keep-list is dead
# weight in an image that ingests local CSV into local deep storage: no HDFS,
# S3, Azure, GCS, Kafka, Kinesis, Kubernetes, Avro, ORC, Protobuf, Kerberos or
# security extensions are reachable from anything these images do. The
# entrypoint builds loadList from what the *dataset* asks for and refuses to
# start when that is not in the image, so a trimmed extension can never be
# half-referenced.
#
# The keep-list is one Parquet extension (68 MB), and no dataset shipped today
# loads it -- it is kept because Parquet is the obvious next source format here
# (the DuckDB context already carries nyc-taxi, and this engine ingests that
# file in ~2 minutes once the peon has enough heap), and adding it later
# without this would change the base for every tag. Set
# `--build-arg DRUID_EXTENSIONS=` to drop it, or name others to keep more.
#
# quickstart/ is the tutorial's sample data and specs -- ours are shipped by the
# build instead. LICENSE, NOTICE and licenses/ stay: they are the Apache-2.0
# attribution that must travel with a redistributed binary release.
#
# hadoop-dependencies/ is not deleted because Druid 37 no longer ships it (it
# was dropped when the Hadoop-based indexer left the default distribution);
# the `rm -rf` is written to tolerate its absence in case an older pin is used.
ARG DRUID_EXTENSIONS="druid-parquet-extensions"
RUN cd /opt/druid && \
    rm -rf quickstart hadoop-dependencies && \
    for ext in extensions/*; do \
      keep=0; \
      for want in $DRUID_EXTENSIONS; do \
        [ "$(basename "$ext")" = "$want" ] && keep=1; \
      done; \
      [ "$keep" = 1 ] || rm -rf "$ext"; \
    done && \
    printf '%s\n' $DRUID_EXTENSIONS > /opt/druid/extensions.available

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. the pgFoundry dumps, a CSV export).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) of the source
# files the transform hook consumes. Named SQL_FILES for uniformity with the
# other engines' manifests even though Druid ingests no SQL: for the pgsql
# datasets these are the .sql dumps the hook parses, and for the CSV/TSV
# datasets they are the data files themselves.
ARG SQL_FILES
# apk packages beyond the shared set (e.g. "python3" for the pgsql hook).
ARG EXTRA_PREREQS

# Where the transform hooks write what the image will ship: one CSV per table
# under $DATA_DIR and one native batch ingestion spec per table under
# $SPEC_DIR. Exported so the hooks (and their unit tests, which override them)
# never hardcode the layout.
ENV DRUID_DATASET_DIR=/druid-dataset
ENV DATA_DIR=/druid-dataset/data
ENV SPEC_DIR=/druid-dataset/specs
# Where those data files end up in the final image. An ingestion spec's
# inputSource names a path that has to resolve at *run* time, not build time,
# so the two are separate settings.
ENV RUNTIME_DATA_DIR=/opt/druid/dataset/data

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
# optional dataset extract hook (e.g. geonames' zip unpack).
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

# TRANSFORM. The per-dataset hook turns the extracted sources into the two
# things this engine ships -- $DATA_DIR/<table>.csv and $SPEC_DIR/<table>.json.
# Unlike the other engines' transforms this one is not optional: Druid ingests
# nothing without a spec, so a dataset with no transform hook has nothing to
# load and the LOAD step below says so.
RUN bash -c ' \
      set -e; \
      mkdir -p "$DATA_DIR" "$SPEC_DIR"; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the artifacts the image ships and sanity-check them: every
# spec must have its data file and vice versa, and there must be at least one
# of each -- a dataset that produced no spec would otherwise build fine and then
# boot into an empty cluster. An optional dataset load hook runs last (e.g. to
# write a per-dataset extension load list).
RUN bash -c ' \
      set -e; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi; \
      n=0; \
      for spec in "$SPEC_DIR"/*.json; do \
        [ -e "$spec" ] || { echo "error: ${DATASET}: transform produced no ingestion specs" >&2; exit 1; }; \
        t="$(basename "$spec" .json)"; \
        [ -f "${DATA_DIR}/${t}.csv" ] || { echo "error: ${DATASET}: spec ${t}.json has no ${t}.csv" >&2; exit 1; }; \
        n=$((n + 1)); \
      done; \
      for data in "$DATA_DIR"/*.csv; do \
        t="$(basename "$data" .csv)"; \
        [ -f "${SPEC_DIR}/${t}.json" ] || { echo "error: ${DATASET}: ${t}.csv has no ingestion spec" >&2; exit 1; }; \
      done; \
      echo "${DATASET}: ${n} datasource(s) to ingest"'

# ---------------------------------------------------------------------------
# Final image: multi-arch Temurin JRE + the trimmed Druid + the dataset.
# ---------------------------------------------------------------------------
# Java 21 rather than 17: Druid 37 supports both, but `eclipse-temurin:17-jre-
# alpine` is published for amd64 only, and this repo ships both architectures.
# Alpine rather than the glibc variants purely for size (~180 MB against
# ~280 MB); Druid is pure Java, and the one place musl shows up -- the
# distribution's bash scripts -- is covered by the `bash` package below.
FROM eclipse-temurin:21-jre-alpine

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="Apache Druid images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/druid-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/druid-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

# bash: the distribution's own launchers (bin/run-java, bin/run-zk, bin/java-util)
#       are `#!/bin/bash` scripts, and the entrypoint runs them rather than
#       reinventing the classpath and the Java 17+ --add-opens flags they set.
#       The official image solves the same problem by downloading a static bash;
#       on Alpine the package is 1 MB and needs no extra download.
# curl: the entrypoint talks to Druid's own HTTP APIs (submit task, poll status,
#       poll load status, query SQL) and the smoke test queries through it too.
#       BusyBox wget cannot POST a JSON body portably.
# The druid user mirrors the official image (uid/gid 1000, home /opt/druid) so a
# bind-mounted var/ directory has the ownership people expect.
RUN apk add --no-cache bash curl && \
    addgroup -S -g 1000 druid && \
    adduser -S -u 1000 -D -H -h /opt/druid -s /bin/sh -G druid druid

COPY --from=engine --chown=druid:druid /opt/druid /opt/druid
# One CSV + one ingestion spec per table, submitted on first boot.
COPY --from=builder --chown=druid:druid /druid-dataset /opt/druid/dataset
# The supervisor, at the same top-level path the official image puts druid.sh.
COPY --chown=druid:druid --chmod=0755 druid-dataset.sh /druid-dataset.sh

ARG DATASET
# Read by the entrypoint (which ingests every spec and names the ready marker
# after it) and recorded so `docker inspect` shows which dataset an image
# carries, matching the other engines.
ENV DATASET=${DATASET}

# Every service writes under var/: Derby metadata, local deep storage, the
# segment cache, task working dirs, ZooKeeper's data dir and the logs. Not
# declared as a VOLUME (unlike the official image): these are throwaway
# practice images, and a VOLUME would leave an anonymous volume behind on every
# `docker run`.
RUN mkdir -p /opt/druid/var && chown druid:druid /opt/druid/var

USER druid
WORKDIR /opt/druid

# The router: one endpoint for the SQL/JSON APIs, the task APIs (it proxies to
# the Overlord/Coordinator) and the web console.
EXPOSE 8888

ENTRYPOINT ["/druid-dataset.sh"]
