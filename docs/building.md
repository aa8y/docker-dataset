# Building images

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:
```
dave build -c postgres -t dellstore
```
The recommended way to add or change a dataset is to declare its `extractUrl`, `sqlFiles` and any extras (`extraPrereqs`, `dbExtension`, `cdDir`) under a new tag in `manifest.yml` — the [ETL Dockerfile](../postgres/Dockerfile) reads them as build args. You can also invoke `docker build` directly by passing those same args, e.g.:
```
docker build -t aa8y/postgres-dataset:world postgres \
  --build-arg DATASET=world \
  --build-arg EXTRACT_URL=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/world/world-1.0/world-1.0.tar.gz \
  --build-arg SQL_FILES=dbsamples-0.1/world/world.sql
```
and then following the same steps for using your custom image as in that engine's README ([PostgreSQL](../postgres/README.md#usage), [MySQL](../mysql/README.md#usage), [CockroachDB](../cockroach/README.md#usage), [SQLite](../sqlite/README.md#usage)).

Swap `-c postgres` (and the `postgres` build context) for `mysql`, `cockroach`, or `sqlite` to build the other engines.

## Build caching

Every tag uses a [registry build cache](https://docs.docker.com/build/cache/backends/registry/)
so the expensive `EXTRACT` layer (the upstream download) and the
`TRANSFORM`/`LOAD` layers after it are reused across builds instead of being
redone from scratch on every CI run. The cache is read on `dave build`
(`--cache-from`) and written on `dave push` (`--cache-to ... mode=max`),
stored per tag as `<repository>:buildcache-<tag>`. A missing cache ref is a
cache miss, not an error, so the first build of a new tag simply populates it.

Correctness is gated on the dataset's actual upstream content. Before each
build, `bin/dataset-checksum` computes a cheap, stable fingerprint of the
tag's source(s) — the `git ls-remote` HEAD SHA for `*.git` sources, the real
`md5`/`sha1` from [archive.org's JSON metadata API](https://archive.org/developers/md-read.html)
(via `jq`) for the Stack Exchange dumps, or the
`ETag`/`Last-Modified`/`Content-Length` from an HTTP `HEAD` (with a ranged-GET
fallback) for other file URLs — without downloading the data. The fingerprint is
passed to the build as the `DATASET_CHECKSUM` build arg, which the builder
references just before `EXTRACT`:

* when the upstream is unchanged, the fingerprint is identical and the cached
  layers are reused (fast);
* when the upstream changes, the fingerprint changes, busting `EXTRACT` and
  cascading a rebuild through `TRANSFORM` and `LOAD` (fresh).

The fingerprint is recorded on the final image as the
`org.opencontainers.image.revision` label (`docker inspect`). The computation
is fail-open: a source that exposes no usable metadata (or is momentarily
unreachable) collapses to a stable marker and caches as before rather than
forcing a spurious full rebuild. The script needs `curl`, `jq`, and `git` on
the host (all present on the CI runners; `jq` is already required by the
integration tests).
