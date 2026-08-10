# CockroachDB images — `aa8y/cockroach-dataset`

The CockroachDB images mirror the PostgreSQL ones — one dataset per image, same ETL [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml). The engine is [CockroachDB](https://www.cockroachlabs.com/) (see [Base image](#base-image) for that choice); it is PostgreSQL wire- and SQL-compatible, so these reuse the same PostgreSQL-dialect dumps the Yugabyte PostgreSQL tags do. The official `cockroachdb/cockroach` entrypoint creates the database named by the `COCKROACH_DATABASE` env var and runs every `/docker-entrypoint-initdb.d/*.sql` script against it (under `start-single-node`), so — unlike the postgres images — the build emits no `CREATE DATABASE` header; the database is the bare dataset name.

The available tags are the CockroachDB column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[CockroachDB](https://www.cockroachlabs.com/) as [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset). There is no official Alpine image (the official [`cockroachdb/cockroach`](https://hub.docker.com/r/cockroachdb/cockroach) image is UBI-minimal), but it is slim (~170 MB) and multi-arch, and its entrypoint honours the same `/docker-entrypoint-initdb.d/*.sql` convention as the official postgres image (plus a `COCKROACH_DATABASE` env var) when the container is started with `start-single-node`. CockroachDB is PostgreSQL wire- and SQL-compatible, so the dataset pattern carries over and these reuse the same PostgreSQL-dialect sample dumps.

## Usage

The images run a single-node cluster in insecure mode (these are throwaway practice/test images, mirroring the trivial credentials the postgres/mysql images use), which keeps connecting simple. Start a container and connect with the built-in `cockroach sql` client:
```
docker run -d --name cr-ds-<tag> aa8y/cockroach-dataset:<tag>
docker exec -it cr-ds-<tag> cockroach sql --insecure --database <db_name>
```
where `<tag>` is one of the tags in the CockroachDB column of the [matrix](../README.md#dataset-support-matrix) and `<db_name>` is the matching dataset name (the tag minus any `stackexchange-` prefix, e.g. `stackexchange-beer` → `beer`).

## CockroachDB datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are CockroachDB-specific:

* `chinook`, `northwind`: same Yugabyte PostgreSQL-dialect dumps as the postgres `yugabyte-chinook` / `yugabyte-northwind` tags (quoted CamelCase identifiers for chinook; snake_case for northwind).
* `world`, `iso3166`, `frenchtowns`, `usda`, `dellstore`: pgFoundry PostgreSQL DDL + data dumps, transcoded from Latin-1 to UTF-8, stripped of Postgres session settings and `setval` calls CockroachDB does not need, with `COPY` blocks rewritten to batched `INSERT`s at build time (`cockroach/scripts/pgfoundry`; CRDB's init-time stdin `COPY` is far slower than Postgres for large blocks). The dellstore PL/pgSQL helper function is dropped (schema and data still load faithfully).
* `pgexercises`: the Yugabyte `clubdata` sample (3 tables in a dedicated `cd` schema).
* `sportsdb`: the Yugabyte sportsdb mirror (107 tables created; only generic infrastructure plus American football, baseball, basketball, and ice hockey carry data). Yugabyte `USING lsm` indexes are rewritten to `btree` at build time; an unused `CREATE DOMAIN` is dropped.
* `moma`: schema authored in-repo (`cockroach/scripts/moma/schema.sql`, every column `text`); the CSV exports are read at build time and baked into the init script as batched `INSERT`s (CockroachDB's SQL client supports neither `\copy` nor `COPY FROM '<file>'`). Counts drift as MoMA refreshes its exports (recorded as floors).
* `geonames`: schema authored in-repo (`cockroach/scripts/geonames/schema.sql`); the tab-separated export is shipped in the node's external-IO dir and bulk-loaded with `IMPORT INTO ... DELIMITED DATA` (the TSV form of CRDB's bulk path — the export has no quoting, so a double quote in a place name is a literal character). Counts drift as GeoNames rebuilds the dump daily (recorded as floors).
* `openflights`: schema authored in-repo (`cockroach/scripts/openflights/schema.sql`, 3 tables); the published files are already RFC4180 CSV, so they are shipped to the node's external-IO dir and bulk-loaded with `IMPORT INTO ... CSV DATA` unchanged (`nullif` maps their `\N` to `NULL`). No foreign keys (`routes` deliberately keeps dangling airport/airline references). Counts drift as upstream refreshes the files (recorded as floors).
* `stackexchange-<site>` (db = bare site name): per-table XML converted at build time by the shared cockroach stackexchange hook to `CREATE TABLE` + batched `INSERT`s + indexes (8 tables in `public`); Postgres' hook emits `COPY` instead, but CRDB's init-time stdin `COPY` is far slower for large blocks. Counts are recorded as floors. `cooking` is the largest.

## Datasets not ported to CockroachDB

The remaining datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features CockroachDB does not support faithfully:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL with range-partitioned tables; MySQL and SQLite use native Sakila ports directly (tag `sakila`).
* `adventureworks`: the only maintained open port targets PostgreSQL; its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to load on CockroachDB without divergence.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows).
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) relies on the `tsm_system_rows` extension (no CockroachDB equivalent), so a port would have to drop the upstream views.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c cockroach -t dellstore
```

To add or change a CockroachDB dataset, declare its `extractUrl`, `sqlFiles` and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
