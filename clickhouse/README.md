# ClickHouse images — `aa8y/clickhouse-dataset`

The ClickHouse images follow the same one-dataset-per-image model, and — like the PostgreSQL, MySQL and CockroachDB ones — load at first container start: the build assembles an init script (plus any data files it reads) and the official entrypoint runs it against a fresh server. What is different is the engine underneath. [ClickHouse](https://clickhouse.com/) is a columnar OLAP database, so it is the first engine here whose *data model*, not just its SQL spelling, diverges from the PostgreSQL sample dumps: every table names a storage engine (`MergeTree`) and a sorting key, columns are `NOT NULL` unless declared `Nullable`, and there are no constraints, sequences or ordinary secondary indexes. The dumps therefore go through a real dialect translation ([`scripts/pgsql`](scripts/pgsql/transform)) rather than the thin filters the DuckDB and CockroachDB images use.

Each [`aa8y/clickhouse-dataset`](https://hub.docker.com/r/aa8y/clickhouse-dataset) image carries exactly one dataset in one database, built through the [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml).

The available tags are the ClickHouse column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[ClickHouse](https://clickhouse.com/) as [`aa8y/clickhouse-dataset`](https://hub.docker.com/r/aa8y/clickhouse-dataset), built on the official [`clickhouse/clickhouse-server`](https://hub.docker.com/r/clickhouse/clickhouse-server) **Alpine** image (multi-arch amd64 + arm64, ~232 MB, pinned in the [Dockerfile](Dockerfile) to a release on the current LTS line). Its entrypoint honours the same `/docker-entrypoint-initdb.d` convention the official postgres image does: on a first start with an empty data dir it brings up a temporary server bound to `127.0.0.1`, creates the database named by `CLICKHOUSE_DB`, feeds every `*.sql` file in that directory to `clickhouse-client --multiquery`, and only then restarts the real server on all interfaces.

That "only then" matters twice over. It is why nothing outside the container can observe a half-loaded database — and it is also why the smoke test's readiness probe pings the container's own `eth0` address rather than `localhost`, since a `localhost` query would succeed in the middle of the load.

`/var/lib/clickhouse` is a `VOLUME` in the base image, so a data directory baked at build time would be shadowed the moment the container ran; that is the reason these images ship an init script rather than a prebuilt database like the SQLite and DuckDB ones.

## Usage

Start a container and connect with the built-in `clickhouse-client`:
```
docker run -d --name ch-ds-world aa8y/clickhouse-dataset:world
docker exec -it ch-ds-world clickhouse-client -d world
```
where the tag is one of the tags in the ClickHouse column of the [matrix](../README.md#dataset-support-matrix) and the database is the matching dataset name (the tag minus any `stackexchange-` prefix, e.g. `stackexchange-beer` → `beer`).

The images keep the base image's stock `default` user: **no password, reachable from any address** (`CLICKHOUSE_SKIP_USER_SETUP=1`). These are throwaway practice and test images, mirroring the trivial credentials the postgres and mysql images use and the insecure mode the cockroach ones run in; left to itself the entrypoint would restrict `default` to `127.0.0.1`, which would make these the only images here you could not reach over a published port. So you can also connect from outside:
```
docker run -d --name ch-ds-world -p 8123:8123 -p 9000:9000 aa8y/clickhouse-dataset:world
curl 'http://localhost:8123/?database=world' --data-binary 'SELECT count() FROM city'
```
Don't put them anywhere that matters.

The first container start runs the load, so give it a moment before querying — a second or two for the small datasets, up to a minute or so for `stackexchange-cooking` (see the per-dataset notes below).

## ClickHouse datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are ClickHouse-specific.

* `world`, `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`, `chinook`: the same PostgreSQL dumps the DuckDB and CockroachDB tags use, run through the shared [`scripts/pgsql`](scripts/pgsql/transform) transform hook. That hook is where all the engine-specific work lives, and its module docstring is the full account; in short it rebuilds every `CREATE TABLE` with ClickHouse types and `ENGINE = MergeTree`, turns the dump's primary key into the **sorting key** (collected in a first pass, because `pg_dump` writes `ALTER TABLE ... ADD PRIMARY KEY` *after* the data), makes every column `Nullable` unless it says `NOT NULL` — except a sorting-key column, which MergeTree refuses to let be nullable — converts `COPY ... FROM stdin` blocks and chinook's 15,607 single-row `INSERT`s into batched multi-row `INSERT`s, and doubles every backslash in a string literal, since ClickHouse reads escape sequences where PostgreSQL (with `standard_conforming_strings`) does not. Row counts match the PostgreSQL and DuckDB tags exactly.
  * Worth knowing why the rewrite is a rewrite and not a filter: ClickHouse 26.8 would *accept* most of a pgFoundry `CREATE TABLE` as it stands — it takes PostgreSQL's type spellings as aliases, takes `NOT NULL`, and with `default_table_engine = MergeTree` takes a statement with no engine at all. It would then store every `NULL` as the type's zero (a nullable `smallint` becomes `0`, a `timestamp` becomes `1970-01-01`), give every table `ORDER BY tuple()` — no sorting key — and clamp `date`/`timestamp` values from before 1970 to the epoch. None of that shows up in a row count, which is exactly why the hook is explicit about all three.
  * A table with no primary key upstream gets `ORDER BY tuple()`, MergeTree's documented "no sorting key": all three `frenchtowns` tables (they declare only `UNIQUE`), `usda`'s `footnote`, and `iso3166`'s `subcountry`.
  * `frenchtowns` table names are lower-case (`regions`, `departments`, `towns`) where the DuckDB tag keeps the dump's `Regions`/`Departments`/`Towns`. The dump declares them unquoted and then `COPY`s into the lower-cased spelling, which is consistent only because PostgreSQL folds unquoted identifiers; ClickHouse folds nothing, so the hook applies PostgreSQL's own rule. `chinook`'s quoted CamelCase (`InvoiceLine`, `PlaylistTrack`) is kept verbatim for the same reason.
  * `date` becomes `Date32` and `timestamp` becomes `DateTime64(6)` rather than the plain `Date`/`DateTime`, both of which start at 1970-01-01 — chinook's `Employee.BirthDate` runs back to 1947.
  * Foreign keys, `UNIQUE`, `CHECK`, `DEFAULT`, sequences, `CREATE INDEX` and the dellstore PL/pgSQL helper function are dropped: ClickHouse has no equivalent for any of them, and none is needed to reproduce the data.
* `nyc-taxi`: the NYC TLC yellow-taxi trip records — **4,322,960 rows** in one `trips` table, keyed on `tpep_pickup_datetime`, and the tag that shows what this engine is for. The month is **pinned** (`yellow_tripdata_2025-06.parquet`) because TLC publishes monthly and revises older months in place. The [`scripts/nyc_taxi`](scripts/nyc_taxi/transform) hook writes an explicit `CREATE TABLE` — the TLC's own column names, types read out of the Parquet schema with `clickhouse-local` — and the `INSERT ... FROM INFILE ... FORMAT Parquet` that loads it; the 73.5 MB Parquet file ships in the image, because unlike DuckDB this engine loads at container start. Boot to ready is about 10 seconds.
  * The database is **`nyc_taxi`**, with an underscore, while the tag keeps the hyphen every other engine uses. The entrypoint interpolates `CLICKHOUSE_DB` straight into `CREATE DATABASE IF NOT EXISTS $CLICKHOUSE_DB` with no quoting, and `nyc-taxi` there parses as a subtraction.
* `moma`: the MoMA research collection, published only as CSV, so the schema is authored in-repo ([`scripts/moma`](scripts/moma/schema.sql)) with the same two tables and column order as the other engines, every column `String`. The CSVs ship next to the init script and are read at start with `INSERT ... FROM INFILE ... FORMAT CSV`, positionally with the header line skipped — MoMA's header spells its columns `ConstituentID`, `DisplayName`, even `Wiki QID`, so the name-matching `CSVWithNames` would quietly leave the snake_case columns empty. Counts drift as MoMA refreshes its exports, so the smoke test records floors.
* `geonames`: schema authored in-repo ([`scripts/geonames`](scripts/geonames/schema.sql)); the tab-separated export ships alongside the init script and is loaded with `FORMAT TabSeparated` (the export has no quoting at all, so a double quote in a place name is a literal character). The load is bracketed by `SET format_tsv_null_representation = ''`: the export marks a missing value with a blank field rather than TSV's `\N`, and without the override a blank would land as `0` in the nullable integer columns — turning "not recorded" into "sea level" for `elevation`. Counts drift as GeoNames rebuilds the dump daily (floors).
* `openflights`: schema authored in-repo ([`scripts/openflights`](scripts/openflights/schema.sql), 3 tables); the published files are already RFC4180 CSV and their `\N` sentinel is ClickHouse's own default CSV null representation, so they load unchanged with `FORMAT CSV`. No foreign keys — `routes` deliberately keeps dangling airport/airline references — and ClickHouse would have none to declare anyway. Counts drift as upstream refreshes the files (floors).
* `stackexchange-<site>` (`beer`, `chess`, `coffee`, `cooking`, `poker`, `woodworking`, `outdoors`, `boardgames`): per-table XML converted at build time by [`scripts/stackexchange`](scripts/stackexchange/transform) into 8 `MergeTree` tables keyed on `Id` plus batched `INSERT`s. Two differences from the other engines' emitters: the dozen-odd `CREATE INDEX` statements are gone (ClickHouse's `CREATE INDEX` declares a *data-skipping* index with different semantics, and the sorting key already does the lookup job), and backslashes are doubled so a post body full of code survives intact. `CreationDate` and friends are `DateTime64(3)`, matching the milliseconds the dumps carry; the ISO-8601 `T` goes in as-is. Counts drift as archive.org refreshes the dumps, so the smoke test records floors. `cooking` is by far the largest — about 1.1 M rows, and roughly 80 seconds from `docker run` to a queryable database.

## Datasets not ported to ClickHouse

The remaining datasets need either a source ClickHouse cannot ingest as published or a schema whose shape does not survive the translation:

* `northwind`: the Yugabyte dump the postgres/cockroach tags use declares `bytea` columns (`categories.picture`, `employees.photo`), which ClickHouse has no type for — they would have to become `String` holding the dump's `'\x…'` hex text. It also writes its data as `INSERT INTO public.categories VALUES` with **no column list**, which the shared `scripts/pgsql` hook relies on to rewrite an INSERT's identifiers. Both are dataset-specific work rather than rules the shared hook can carry.
* `sportsdb`: 107 tables, most of them empty, built around Yugabyte's `USING lsm` indexes and a `CREATE DOMAIN`. The translation would produce 107 `MergeTree` tables with `ORDER BY tuple()` for the majority that declare no primary key — a large, slow image that shows nothing about this engine.
* `sakila` / `pagila`: `pagila` is a PostgreSQL port of Sakila built on range-**partitioned** tables, custom domains, triggers and a `vector` extension column. ClickHouse partitions differently (a `PARTITION BY` expression on a MergeTree, not child tables) and has none of the rest, so the result would be a different database with the same table names.
* `employees`: the upstream loader is a MySQL client script (`source` directives over six data files) rather than a portable dump.
* `adventureworks`: the only maintained open port targets PostgreSQL and relies on multiple schemas, materialized views and a Python reformat step — ClickHouse's namespace *is* the database, so the multi-schema layout has nowhere to go.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is a binary-ish `pg_dump` leaning on `jsonb` and PostgreSQL-specific functions.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) relies on the `tsm_system_rows` extension and ships views that assume PostgreSQL semantics.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c clickhouse -t world
```

To add or change a ClickHouse dataset, declare its `extractUrl`, `sqlFiles` and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. Note that the dataset name becomes the database name and is interpolated into SQL unquoted by the base image's entrypoint, so it has to be a bare ClickHouse identifier. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
