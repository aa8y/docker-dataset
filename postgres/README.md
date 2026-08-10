# PostgreSQL images — `aa8y/postgres-dataset`

The original images: each [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) image carries exactly one dataset, loaded into a database named after the dataset, and is built through an Extract -> Transform -> Load [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml).

The available tags are the PostgreSQL column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[PostgreSQL](https://www.postgresql.org/) as [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset). We use the `alpine` version of the official image as the base image to keep our image slim.

## Usage

You can start the container by running:
```
docker run -d --name pg-ds-<tag> aa8y/postgres-dataset:<tag>
```
and access it by:
```
docker exec -it pg-ds-<tag> psql -d <db_name>
```
where `<tag>` is one of the tags in the [matrix](../README.md#dataset-support-matrix) and `<db_name>` is the dataset baked into it — the tag itself, minus any `yugabyte-`/`stackexchange-` prefix (e.g. `yugabyte-chinook` → `chinook`, `stackexchange-beer` → `beer`). You can also use them with `docker-compose`. See [this example](https://github.com/aa8y/data-dude/blob/master/docker-compose.yml) for information on how to use them.

## PostgreSQL datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are PostgreSQL-specific.

* `yugabyte-chinook` (db `chinook`): 11 tables in the `public` schema, quoted CamelCase identifiers (e.g. `"Track"`, `"InvoiceLine"`).
* `yugabyte-pgexercises` (db `pgexercises`): 3 tables in a dedicated `cd` schema (not `public`).
* `sportsdb` / `yugabyte-sportsdb`: all 107 tables are created, but only the generic infrastructure tables plus American football, baseball, basketball, and ice hockey carry data — motor racing, soccer, tennis, wagering, and weather are schema-only.
* `pagila`: the `payment` table is range-partitioned by month (`payment_p2022_NN`), so row counts split across the parent and its partitions; upstream periodically shifts the sample dates to the current year, so absolute dates change between rebuilds.
* `omdb`: CSVs are fetched at build time and shipped in the image so `\copy` resolves at start; the init script creates the `tsm_system_rows` extension the upstream views rely on. Heavy (~150 MB of CSV + indexes).
* `adventureworks`: the upstream port pulls Microsoft's CSV bundle and runs a Python reformat before loading (68 tables across 5 schemas). Heavy (~90 MB of CSV).
* `airlines`: 9 tables in a `bookings` schema (`search_path` defaults to it). Upstream ships a single gzipped `pg_dump` of its own `demo` database, so the build decompresses it and strips the `DROP/CREATE DATABASE` / `\connect` directives so it loads into the `airlines` database. The heaviest dataset (several million inlined rows); the snapshot URL is date-stamped and may need bumping if postgrespro retires the pinned file.
* `moma`: MoMA ships only CSV/JSON, so the schema is authored in-repo (`postgres/scripts/moma/schema.sql`, every column `text`) and the CSVs ship alongside the init script; counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>` (db = bare site name): the dump ships only per-table XML, so a shared build hook (`postgres/scripts/stackexchange/transform`) converts it to `CREATE TABLE` + inline `COPY` + indexes at build time (8 tables in `public`). Every site shares one schema and builds through that one hook, so adding a site is just another tag; counts are recorded as floors. `cooking` is the largest (~500k votes, ~230k post-history rows).

## Tag naming

The database inside each image is the bare dataset name — the tag minus any `yugabyte-`/`stackexchange-` prefix. Those source prefixes exist so a dataset could ship from a second mirror later; `sportsdb` and `yugabyte-sportsdb` are the same image today, with the unprefixed `sportsdb` kept as a backwards-compatible alias.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c postgres -t dellstore
```

To add or change a PostgreSQL dataset, declare its `extractUrl`, `sqlFiles` and any extras (`extraPrereqs`, `dbExtension`, `cdDir`) under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. See [docs/building.md](../docs/building.md) for the full build instructions, the equivalent raw `docker build` invocation, and how the build cache works.

## History

There is no multi-dataset `all` image anymore — each image is one dataset; for several at once, run one container per dataset (e.g. via `docker-compose`). `pagila` was [removed in 2019](https://github.com/aa8y/docker-dataset/issues/1) over an upstream breakage and is back as a regular tag, since the [fork](https://github.com/devrimgunduz/pagila) loads cleanly on modern Postgres and one dataset can no longer break the others.
