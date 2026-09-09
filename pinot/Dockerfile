# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# The builder stage runs Extract -> Transform -> Load as three distinct RUN
# steps driven entirely by build args from manifest.yml, exactly as in
# ../postgres/Dockerfile and ../cockroach/Dockerfile, and the final stage COPYs
# the assembled artifacts onto the official Apache Pinot image. Build tools live
# only in the builder, so the final image never carries them.
#
# Engine note, and why the LOAD step here assembles *data files* rather than an
# init script. Pinot is not a SQL database with a bulk-load path bolted on; it
# is a distributed OLAP store whose unit of storage is an immutable **segment**
# and whose DDL is not SQL at all. A table is declared by two JSON documents --
# a schema (column names and Pinot data types) and a table config (segment,
# index and tenant settings) -- POSTed to a running controller, and it is filled
# by building a segment from a data file and pushing it. There is no CREATE
# TABLE to run and no `/docker-entrypoint-initdb.d` in the official image, whose
# entrypoint is `pinot-admin.sh`, a CLI multiplexer.
#
# So the split between build and run lands in a different place than for the
# other server engines. The build authors, per source table, a CSV of the rows
# plus that pair of JSON documents plus a manifest recording each table's exact
# row count (scripts/<dataset>/transform); the ../pinot/entrypoint script starts
# a one-container cluster at container start, replays the artifacts against it
# over REST, and waits for every table to reach its recorded count before
# printing its ready marker. That is still the repo's init-at-start model -- the
# image ships a dataset, not a database -- just carried over REST instead of
# over a SQL client.
#
# Nothing here names a specific dataset. Most are fully described by
# EXTRACT_URL + SQL_FILES; the rest plug into the ETL steps via the
# convention-located scripts/<dataset>/{extract,transform,load} hooks (run at
# the matching stage if present, keyed on $DATASET).
#
# Data Sources.
# PG Foundry: https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/
#             (world, iso3166, frenchtowns, usda, dellstore -- PostgreSQL DDL
#             plus COPY data, which scripts/pgsql decompiles into per-table
#             CSV + Pinot schema + table config.)
# PGExercises:
#             https://github.com/yugabyte/yugabyte-db/tree/master/sample
#             (the clubdata sample; the same shape, but with the data as
#             multi-row INSERTs rather than COPY.)

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of files
# to fetch individually (e.g. the pgexercises .sql pair).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) of the source files
# the transform hook consumes. Named SQL_FILES for uniformity with every other
# engine's manifest block even where the inputs are not SQL: for the pgsql
# family these are the PostgreSQL dumps, and the hook reads the name straight
# out of the environment.
ARG SQL_FILES
# apk packages beyond the shared set (python3 for the transform hooks).
# Builder-only: hooks that run here can rely on them, the final image cannot.
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

# TRANSFORM. The dataset transform hook, which is where the whole engine-shaped
# conversion happens: it writes ./dataset/<table>.{csv,schema.json,table.json}
# plus ./dataset/tables.tsv. Unlike the other engines there is no generic
# fallback -- there is nothing sensible to do with an unconverted PostgreSQL
# dump on Pinot -- so the hook is required and LOAD below fails without it.
RUN bash -c ' \
      set -e; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Assemble the artifacts the final image ships, then run an optional
# dataset load hook (for anything that has to sit outside /dataset). The
# manifest check is the build's own smoke test: an empty or missing tables.tsv
# means the transform produced no tables, which would otherwise surface only as
# an image that boots and serves nothing.
RUN bash -c ' \
      set -e; \
      mkdir -p /dataset; \
      if [ -d dataset ]; then cp -a dataset/. /dataset/; fi; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi; \
      if [ ! -s /dataset/tables.tsv ]; then \
        echo "error: no tables produced for ${DATASET} (empty /dataset/tables.tsv)" >&2; exit 1; \
      fi; \
      echo "assembled $(wc -l < /dataset/tables.tsv) tables for ${DATASET}"'

# ---------------------------------------------------------------------------
# Final image: official Apache Pinot + the dataset artifacts and the wrapper.
# ---------------------------------------------------------------------------
# The official image is the only practical base: Pinot is a JVM application
# assembled from ~40 plugin jars, there is no slim or Alpine variant published,
# and rebuilding the distribution to shave it would mean maintaining a fork of
# someone else's release. It is heavy (~2.6 GB on disk, Java 21 plus the full
# plugin set), but every tag in this repository shares those layers, so the cost
# is paid once per host rather than once per dataset.
FROM apachepinot/pinot:1.5.0

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="Apache Pinot images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/pinot-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/pinot-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# Read by the entrypoint for its ready marker, and recorded so `docker inspect`
# shows which dataset an image carries, matching the other engines.
ENV DATASET=${DATASET}

# The base image asks for -Xms4G -Xmx4G, which is a production-cluster figure
# and more than most laptops or CI runners will hand a single container. These
# images run one node holding one sample dataset, and OFFLINE segments are
# memory-mapped rather than heaped, so the heap only has to cover query
# execution and the largest single segment build. Measured peak *container*
# usage (both JVMs, heap and non-heap) across the shipped tags runs 1.04 GB for
# iso3166 to 1.30 GB for moma -- the widest table here, 160k rows of 30 text
# columns -- so 2 GB leaves headroom without reserving memory nothing uses.
# -Dpinot.admin.system.exit=false is carried over from the base image: without
# it pinot-admin.sh calls System.exit after a subcommand returns, which would
# tear down the cluster the moment StartServiceManager finishes bootstrapping.
ENV JAVA_OPTS="-Xms512M -Xmx2G -Dpinot.admin.system.exit=false"

# Service configs for the one-container topology (controller + broker + server
# against a local ZooKeeper), overwriting the base image's stock samples of the
# same name. Ports are unchanged from upstream; see the files for what differs.
COPY conf/controller.conf conf/broker.conf conf/server.conf /opt/pinot/conf/

# The dataset: per-table CSV, Pinot schema, OFFLINE table config, and the
# tables.tsv manifest of exact row counts.
COPY --from=builder /dataset /opt/pinot/dataset

COPY entrypoint /usr/local/bin/pinot-dataset-entrypoint

# Replaces the base image's `./bin/pinot-admin.sh` + `-help` pair. A bare
# `docker run` starts the cluster and loads the dataset; the wrapper still
# forwards any arguments to pinot-admin.sh, so the base image's own interface
# (`docker run <image> QuickStart -help`, say) keeps working. CMD is emptied so
# the inherited `-help` does not turn every default run into a help screen.
ENTRYPOINT ["/usr/local/bin/pinot-dataset-entrypoint"]
CMD []
