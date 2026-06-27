# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

**Pre-populated sample databases as Docker images** — ready-to-run [PostgreSQL](https://www.postgresql.org/), [MySQL](https://www.mysql.com/), [CockroachDB](https://www.cockroachlabs.com/), and [SQLite](https://www.sqlite.org/) containers loaded with real, valid sample data (Chinook, Northwind, Sakila/Pagila, World, AdventureWorks, Stack Exchange, and more).

Ever needed a database already populated with valid data — to practice SQL, run tests, demo an app, or benchmark — without hand-crafting rows or hunting for a usable dump? Every image ships exactly one dataset in its own database, so you just `docker run` and connect.

## Contents

* [Dataset support matrix](#dataset-support-matrix)
* [Databases](#databases)
* [PostgreSQL images](#postgresql-images)
* [MySQL images](#mysql-images)
* [CockroachDB images](#cockroachdb-images)
* [SQLite images](#sqlite-images)
* [Usage](#usage)
* [Custom images](#custom-images)
* [Testing](#testing)
* [Build caching](#build-caching)
* [Future Work](#future-work)

## Dataset support matrix

Each cell is the image tag to pull for that dataset on that engine; **—** means it isn't shipped there (yet). The dataset name links to its upstream source when every engine pulls from the same one; where engines use different upstreams, the source link is on the individual tag instead. All images are published for `linux/amd64` and `linux/arm64`.

| Dataset | [PostgreSQL](#postgresql-images) | [MySQL](#mysql-images) | [CockroachDB](#cockroachdb-images) | [SQLite](#sqlite-images) |
| --- | --- | --- | --- | --- |
| [AdventureWorks](https://github.com/lorint/AdventureWorks-for-Postgres) | `adventureworks` | — | — | — |
| [Airlines](https://postgrespro.com/education/demodb) | `airlines` | — | — | — |
| Chinook | [`yugabyte-chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) |
| [Dell DVD Store](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `dellstore` | `dellstore` | `dellstore` | `dellstore` |
| [French Towns](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` |
| [ISO 3166](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `iso3166` | `iso3166` | `iso3166` | `iso3166` |
| [MoMA](https://github.com/MuseumofModernArt/collection) | `moma` | `moma` | `moma` | `moma` |
| Northwind | [`yugabyte-northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/dalers/mywind) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/jpwhite3/northwind-SQLite3) |
| [OMDb](https://github.com/df7cb/omdb-postgresql) | `omdb` | — | — | — |
| [PGExercises](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `yugabyte-pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` |
| Sakila / Pagila | [`pagila`](https://github.com/devrimgunduz/pagila) | [`sakila`](https://dev.mysql.com/doc/sakila/en/) | — | [`sakila`](https://github.com/bradleygrant/sakila-sqlite3) |
| [SportsDB](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `sportsdb`, `yugabyte-sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` |
| [Stack Exchange](https://archive.org/details/stackexchange)¹ | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` |
| [USDA](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `usda` | `usda` | `usda` | `usda` |
| World | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://dev.mysql.com/doc/world-setup/en/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) |

¹ `<site>` is one of `beer`, `coffee`, `poker`, `woodworking`, `chess`, `cooking` (e.g. `stackexchange-chess`).

Every engine also publishes a `latest` tag: it tracks `world` on PostgreSQL and MySQL, and `chinook` on CockroachDB and SQLite.

## Databases

Four database engines are supported today, each published as its own image repository. [ClickHouse](https://clickhouse.com/), [DuckDB](https://duckdb.org/), [Apache Druid](https://druid.apache.org/), and [Apache Pinot](https://pinot.apache.org/) are planned — see [Future Work](#future-work).

* [PostgreSQL](https://www.postgresql.org/) as [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset). We use the `alpine` version of the official image as the base image to keep our image slim.
* [MySQL](https://www.mysql.com/) as [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset). There is no official Alpine image for Oracle MySQL (the official `mysql` image is Oracle Linux / Debian based) and Alpine's own package repositories ship [MariaDB](https://mariadb.org/) in place of MySQL, so to keep the "thin, Alpine-based" goal we build on the community [`yobasystems/alpine-mariadb`](https://hub.docker.com/r/yobasystems/alpine-mariadb) image. MariaDB is the MySQL drop-in Alpine substitutes, and its entrypoint honours the same `MYSQL_*` env vars and `/docker-entrypoint-initdb.d/*.sql` convention as the official postgres image, so the dataset pattern carries over unchanged.
* [CockroachDB](https://www.cockroachlabs.com/) as [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset). There is no official Alpine image (the official [`cockroachdb/cockroach`](https://hub.docker.com/r/cockroachdb/cockroach) image is UBI-minimal), but it is slim (~170 MB) and multi-arch, and its entrypoint honours the same `/docker-entrypoint-initdb.d/*.sql` convention as the official postgres image (plus a `COCKROACH_DATABASE` env var) when the container is started with `start-single-node`. CockroachDB is PostgreSQL wire- and SQL-compatible, so the dataset pattern carries over and these reuse the same PostgreSQL-dialect sample dumps.
* [SQLite](https://www.sqlite.org/) as [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset). SQLite is serverless — a database is just a file — so there is no server to boot and no init scripts; the build assembles the database file and the image ships it. We use the Alpine, statically-linked [`keinos/sqlite3`](https://hub.docker.com/r/keinos/sqlite3) image (multi-arch) as the base, keeping the image genuinely thin and Alpine-based.

## PostgreSQL images

The original images: each [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) image carries exactly one dataset, loaded into a database named after the dataset, and is built through an Extract -> Transform -> Load [Dockerfile](postgres/Dockerfile) driven by `manifest.yml`. (Sources are in the [matrix](#dataset-support-matrix); the notes below are PostgreSQL-specific.)

* `yugabyte-chinook` (db `chinook`): 11 tables in the `public` schema, quoted CamelCase identifiers (e.g. `"Track"`, `"InvoiceLine"`).
* `yugabyte-pgexercises` (db `pgexercises`): 3 tables in a dedicated `cd` schema (not `public`).
* `sportsdb` / `yugabyte-sportsdb`: all 107 tables are created, but only the generic infrastructure tables plus American football, baseball, basketball, and ice hockey carry data — motor racing, soccer, tennis, wagering, and weather are schema-only.
* `pagila`: the `payment` table is range-partitioned by month (`payment_p2022_NN`), so row counts split across the parent and its partitions; upstream periodically shifts the sample dates to the current year, so absolute dates change between rebuilds.
* `omdb`: CSVs are fetched at build time and shipped in the image so `\copy` resolves at start; the init script creates the `tsm_system_rows` extension the upstream views rely on. Heavy (~150 MB of CSV + indexes).
* `adventureworks`: the upstream port pulls Microsoft's CSV bundle and runs a Python reformat before loading (68 tables across 5 schemas). Heavy (~90 MB of CSV).
* `airlines`: 9 tables in a `bookings` schema (`search_path` defaults to it). Upstream ships a single gzipped `pg_dump` of its own `demo` database, so the build decompresses it and strips the `DROP/CREATE DATABASE` / `\connect` directives so it loads into the `airlines` database. The heaviest dataset (several million inlined rows); the snapshot URL is date-stamped and may need bumping if postgrespro retires the pinned file.
* `moma`: MoMA ships only CSV/JSON, so the schema is authored in-repo (`postgres/scripts/moma/schema.sql`, every column `text`) and the CSVs ship alongside the init script; counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>` (db = bare site name): the dump ships only per-table XML, so a shared build hook (`postgres/scripts/stackexchange/transform`) converts it to `CREATE TABLE` + inline `COPY` + indexes at build time (8 tables in `public`). Every site shares one schema and builds through that one hook, so adding a site is just another tag; counts are recorded as floors. `cooking` is the largest (~500k votes, ~230k post-history rows).

### Tag naming

The database inside each image is the bare dataset name — the tag minus any `yugabyte-`/`stackexchange-` prefix. Those source prefixes exist so a dataset could ship from a second mirror later; `sportsdb` and `yugabyte-sportsdb` are the same image today, with the unprefixed `sportsdb` kept as a backwards-compatible alias.

### History

There is no multi-dataset `all` image anymore — each image is one dataset; for several at once, run one container per dataset (e.g. via `docker-compose`). `pagila` was [removed in 2019](https://github.com/aa8y/docker-dataset/issues/1) over an upstream breakage and is back as a regular tag, since the [fork](https://github.com/devrimgunduz/pagila) loads cleanly on modern Postgres and one dataset can no longer break the others.

## MySQL images

The MySQL images mirror the PostgreSQL ones — one dataset per image, same ETL [Dockerfile](mysql/Dockerfile) driven by `manifest.yml`. The engine is MariaDB (see [Databases](#databases) for why); it is wire- and SQL-compatible with MySQL for these samples. Because each image is a single dataset, the build strips any database-level DDL the upstream dump ships (`CREATE`/`DROP DATABASE`/`SCHEMA`, `USE`) and loads everything into one database named after the dataset.

Start a container and connect with the `mariadb` (MySQL-compatible) client:
```
docker run -d --name my-ds-<tag> aa8y/mysql-dataset:<tag>
docker exec -it my-ds-<tag> mariadb -uroot -pmysql <db_name>
```
where `<tag>` is one of the tags in the MySQL column of the [matrix](#dataset-support-matrix) and `<db_name>` is the matching dataset name (the tag itself, minus any `stackexchange-` prefix). The root password is `mysql`.

### MySQL datasets

MySQL-native sources, used directly (sources in the [matrix](#dataset-support-matrix); notes below are MySQL-specific):

* `sakila`: stands in for PostgreSQL's `pagila` (which is itself a Sakila port); 16 base tables. `film_text` is populated by an `AFTER INSERT` trigger on `film` rather than by bulk data, and unlike `pagila` the `payment` table is not partitioned.
* `world`: MySQL's native `world` — `city`, `country`, `countrylanguage` (3 tables), identical row counts to the PostgreSQL `world`.
* `chinook`: the vendor's MySQL-specific `Chinook_MySql.sql` (release `v1.4.5`); CamelCase identifiers (e.g. `` `Track` ``), with the script's `CREATE DATABASE Chinook` stripped so it loads into the lowercase `chinook` database.
* `northwind`: the dalers/mywind port of Microsoft's Access sample (snake_case, 20 tables) — a larger conversion than the 14-table PostgreSQL `yugabyte-northwind`.
* `moma`: schema authored in-repo (`mysql/scripts/moma/schema.sql`, every column `text`); CSVs bulk-loaded at start with server-side `LOAD DATA INFILE`. Counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>`: per-table XML converted at build time by a shared hook (`mysql/scripts/stackexchange`) to `CREATE TABLE` + batched `INSERT`s + indexes (CamelCase identifiers). It maps PostgreSQL `int`/`timestamp`/`text` to `INT`/`DATETIME(6)`/`MEDIUMTEXT` and adds a key-prefix length to text-column indexes (MySQL cannot index a full `TEXT`). `cooking` is the largest; counts are recorded as floors.

The remaining datasets have no MySQL-native source, but their PostgreSQL dumps are plain DDL + data, so they are hand-translated at build time through a shared `mysql/scripts/pgsql` transform hook. It converts `COPY` blocks to batched `INSERT`s, rewrites PostgreSQL types to their MySQL equivalents (`character varying`→`varchar`, `timestamp`→`datetime`, `double precision`→`double`, bare `numeric`→`decimal`, and `text`→`varchar(255)` so a text column can serve as a key, which MySQL forbids for `TEXT`), drops PostgreSQL-only noise (sequences, `OWNER TO`, `GRANT`/`REVOKE`, `USING btree`/`hash`/`lsm`, schema qualifiers), lower-cases table identifiers, transcodes Latin-1 dumps to UTF-8, and drops any PL/pgSQL stored functions (no mechanical MySQL translation — the schema and all data still load). Row counts match the PostgreSQL datasets exactly.

* `iso3166`: the `two_letter` country primary key (referenced by `subcountry`) becomes `varchar` so it can be a key.
* `frenchtowns`: the dump declares CamelCase tables but loads lower-case, which the hook reconciles by lower-casing table names; accented commune names survive (the source is UTF-8).
* `usda`: the pgFoundry tarball is Latin-1, so the hook transcodes it to UTF-8 before loading.
* `pgexercises`: upstream lives in a dedicated `cd` schema; the hook strips the `cd.` qualifier so it loads into the single `pgexercises` database.
* `sportsdb`: beyond the usual fixes the hook drops Yugabyte's `USING lsm` index access method and an unused `CREATE DOMAIN`; the 96 unique constraints and 137 foreign keys survive the translation.
* `dellstore`: the dump ships a `new_customer` PL/pgSQL function (an unused app helper); the hook drops it — the schema, keys, and all data still load.

### Datasets not ported to MySQL

The remaining PostgreSQL datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features (PL/pgSQL, extensions, `pg_dump` internals) that can't be hand-translated without diverging from the upstream dataset. Plain DDL + data dumps are instead hand-translated (see the group above); these are the ones that remain PostgreSQL-only:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL, and MySQL uses the original Sakila directly (tag `sakila`, above).
* `adventureworks`: the only maintained open port ([lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres)) targets PostgreSQL. AdventureWorks is a Microsoft SQL Server sample with no comparable, maintained MySQL port, and its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to hand-translate faithfully.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows); it is PostgreSQL-only.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) is PostgreSQL-specific — its views rely on the `tsm_system_rows` extension (no MySQL equivalent), so a port would have to drop them and would no longer be the upstream dataset.
* `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-sportsdb`: superseded on MySQL by the native/ported `chinook`, `northwind`, and `sportsdb` tags above (the Yugabyte SQL is PostgreSQL dialect; `sportsdb` is hand-translated from the same dump, so the prefixed tag is not duplicated here).

## CockroachDB images

The CockroachDB images mirror the PostgreSQL ones — one dataset per image, same ETL [Dockerfile](cockroach/Dockerfile) driven by `manifest.yml`. The engine is [CockroachDB](https://www.cockroachlabs.com/) (see [Databases](#databases) for the base-image choice); it is PostgreSQL wire- and SQL-compatible, so these reuse the same PostgreSQL-dialect dumps the Yugabyte PostgreSQL tags do. The official `cockroachdb/cockroach` entrypoint creates the database named by the `COCKROACH_DATABASE` env var and runs every `/docker-entrypoint-initdb.d/*.sql` script against it (under `start-single-node`), so — unlike the postgres images — the build emits no `CREATE DATABASE` header; the database is the bare dataset name.

The images run a single-node cluster in insecure mode (these are throwaway practice/test images, mirroring the trivial credentials the postgres/mysql images use), which keeps connecting simple. Start a container and connect with the built-in `cockroach sql` client:
```
docker run -d --name cr-ds-<tag> aa8y/cockroach-dataset:<tag>
docker exec -it cr-ds-<tag> cockroach sql --insecure --database <db_name>
```
where `<tag>` is one of the tags in the CockroachDB column of the [matrix](#dataset-support-matrix) and `<db_name>` is the matching dataset name (the tag minus any `stackexchange-` prefix, e.g. `stackexchange-beer` → `beer`).

### CockroachDB datasets

Sources are in the [matrix](#dataset-support-matrix); the notes below are CockroachDB-specific:

* `chinook`, `northwind`: same Yugabyte PostgreSQL-dialect dumps as the postgres `yugabyte-chinook` / `yugabyte-northwind` tags (quoted CamelCase identifiers for chinook; snake_case for northwind).
* `world`, `iso3166`, `frenchtowns`, `usda`, `dellstore`: pgFoundry PostgreSQL DDL + data dumps, transcoded from Latin-1 to UTF-8 and stripped of Postgres session settings CockroachDB does not implement at build time (`cockroach/scripts/pgfoundry`). The dellstore PL/pgSQL helper function is dropped (schema and data still load faithfully).
* `pgexercises`: the Yugabyte `clubdata` sample (3 tables in a dedicated `cd` schema).
* `sportsdb`: the Yugabyte sportsdb mirror (107 tables created; only generic infrastructure plus American football, baseball, basketball, and ice hockey carry data). Yugabyte `USING lsm` indexes are rewritten to `btree` at build time; an unused `CREATE DOMAIN` is dropped.
* `moma`: schema authored in-repo (`postgres/scripts/moma/schema.sql`, every column `text`); CSVs ship alongside the init script so `\copy` resolves at start. Counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>` (db = bare site name): per-table XML converted at build time by the shared postgres stackexchange hook to `CREATE TABLE` + inline `COPY` + indexes (8 tables in `public`). Counts are recorded as floors. `cooking` is the largest.

### Datasets not ported to CockroachDB

The remaining datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features CockroachDB does not support faithfully:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL with range-partitioned tables; MySQL and SQLite use native Sakila ports directly (tag `sakila`).
* `adventureworks`: the only maintained open port targets PostgreSQL; its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to load on CockroachDB without divergence.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows).
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) relies on the `tsm_system_rows` extension (no CockroachDB equivalent), so a port would have to drop the upstream views.

## SQLite images

The SQLite images follow the same one-dataset-per-image model, but since SQLite is serverless the build inverts: rather than shipping init scripts that run at container start, the build assembles the database file and the final image carries it. Each [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset) image carries exactly one dataset as `/data/<dataset>.db`, built through the [Dockerfile](sqlite/Dockerfile) driven by `manifest.yml`: a dataset is described either by a native SQLite SQL script (fed to the `sqlite3` CLI to build the database) or by a prebuilt SQLite database file (shipped as-is).

Start a container and open the database with the bundled `sqlite3` shell:
```
docker run -it --rm aa8y/sqlite-dataset:<tag>
```
which opens `/data/<db_name>.db` directly. You can also run a one-off query:
```
docker run --rm aa8y/sqlite-dataset:<tag> /usr/bin/sqlite3 /data/<db_name>.db "SELECT count(*) FROM ..."
```
where `<tag>` is one of the tags in the SQLite column of the [matrix](#dataset-support-matrix) and `<db_name>` is the matching dataset name.

### SQLite datasets

Sources are in the [matrix](#dataset-support-matrix); the notes below are SQLite-specific:

* `chinook`: built at image-build time from the vendor's native `Chinook_Sqlite.sql` script (release `v1.4.5`); CamelCase identifiers (`Track`, `InvoiceLine`), with row counts matching the other `chinook` tags exactly.
* `northwind`: the prebuilt jpwhite3/northwind-SQLite3 database shipped as-is — the port's *expanded* edition, whose `Orders` and especially `"Order Details"` tables carry far more rows than the classic sample, so this image is heavier than the others.
* `world`: the pgFoundry PostgreSQL `world` dump hand-translated at build time through the shared `sqlite/scripts/pgsql` transform hook (`COPY` → batched `INSERT`s, Postgres-only noise stripped); three tables (`city`, `country`, `countrylanguage`) with row counts matching the other `world` tags exactly.
* `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`, `sportsdb`: same shared `sqlite/scripts/pgsql` hook as `world` — plain PostgreSQL DDL + data dumps rewritten for SQLite at build time. SQLite cannot add constraints via `ALTER TABLE`, so PK/FK/unique constraints from the dump are dropped; tables and row counts still load faithfully (matching the MySQL tags for these datasets).
* `sakila`: the bradleygrant/sakila-sqlite3 port's prebuilt `sakila_master.db` shipped as-is — stands in for PostgreSQL's `pagila` (16 base tables, MySQL-compatible row counts).
* `moma`: schema authored in-repo (`sqlite/scripts/moma/schema.sql`, every column `text`); CSVs bulk-loaded at build time with the sqlite3 CLI's `.import` dot-command. Counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>`: per-table XML converted at build time by a shared hook (`sqlite/scripts/stackexchange`) to `CREATE TABLE` + batched `INSERT`s + indexes (double-quoted CamelCase identifiers). `cooking` is the largest; counts are recorded as floors.

### Datasets not ported to SQLite

The remaining datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features that can't be hand-translated without diverging from the upstream dataset. Plain DDL + data dumps are instead hand-translated (see the group above); these are the ones that remain PostgreSQL-only:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL, and SQLite uses a native Sakila port directly (tag `sakila`, above).
* `adventureworks`: the only maintained open port targets PostgreSQL; AdventureWorks is a Microsoft SQL Server sample with no comparable, maintained SQLite port, and its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to hand-translate faithfully.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows); it is PostgreSQL-only.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) is PostgreSQL-specific — its views rely on the `tsm_system_rows` extension (no SQLite equivalent), so a port would have to drop them and would no longer be the upstream dataset.

## Usage

You can start the container by running:
```
docker run -d --name pg-ds-<tag> aa8y/postgres-dataset:<tag>
```
and access it by:
```
docker exec -it pg-ds-<tag> psql -d <db_name>
```
where `<tag>` is one of the tags in the [matrix](#dataset-support-matrix) and `<db_name>` is the dataset baked into it — the tag itself, minus any `yugabyte-`/`stackexchange-` prefix (e.g. `yugabyte-chinook` → `chinook`, `stackexchange-beer` → `beer`). You can also use them with `docker-compose`. See [this example](https://github.com/aa8y/data-dude/blob/master/docker-compose.yml) for information on how to use them.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in `manifest.yml`). The simplest way to build a tag is through `dave`:
```
dave build -c postgres -t dellstore
```
The recommended way to add or change a dataset is to declare its `extractUrl`, `sqlFiles` and any extras (`extraPrereqs`, `dbExtension`, `cdDir`) under a new tag in `manifest.yml` — the [ETL Dockerfile](postgres/Dockerfile) reads them as build args. You can also invoke `docker build` directly by passing those same args, e.g.:
```
docker build -t aa8y/postgres-dataset:world postgres \
  --build-arg DATASET=world \
  --build-arg EXTRACT_URL=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/world/world-1.0/world-1.0.tar.gz \
  --build-arg SQL_FILES=dbsamples-0.1/world/world.sql
```
and then following the same [aforementioned](#usage) steps for using your custom image.

## Testing

There are two layers of tests.

**Structure tests** are static [container-structure-test][cst] configs under
`test/config/` — a shared `common.yaml` plus one file per dataset. They assert
on the image filesystem and the shipped init scripts without booting Postgres.
The configs to apply per tag are declared in `manifest.yml` under
`structureTest:` and run natively by `dave structure-test`.

**Integration (smoke) tests** actually boot each image and query the live
database. For every dataset shipped in a tag, `test/integration/run.sh`:

1. waits for Postgres to finish initializing (TCP readiness, so all init
   scripts have completed),
2. lists the base tables and asserts the set exactly matches the expected set
   (no missing tables, no unexpected extras), and
3. runs `SELECT count(*)` on every table and asserts the row counts match.

Expected tables and counts live per-dataset as JSON under `test/expected/`,
e.g. `test/expected/iso3166.json`:

```json
{
  "public.country": 242,
  "public.subcountry": 3995
}
```

keyed by schema-qualified table name, with authoritative `count(*)` values.
A value is normally an exact count. For datasets whose data is fetched from a
live upstream at build time and so drifts between builds (`omdb` from
`www.omdb.org`, `moma` from MoMA's CSV exports, and `beer` from the
Stack Exchange data dump), the value is instead a floor like
`">=59274"` and the test asserts `count(*) >=` that number. `--update` writes
floors automatically for such datasets.

These are wired into `dave test` via the `test:` template in `manifest.yml`,
which renders per tag and passes the image tag plus the one dataset baked into
it (`run.sh` still accepts a comma-separated list, so it keeps working if a
multi-dataset image is ever reintroduced). The script needs `docker` and `jq`
on the host; `psql` runs inside the container.

```sh
brew install container-structure-test jq     # one-time

dave build
dave structure-test                           # static checks
dave test                                      # live smoke tests (boots images)

# scope to specific tags locally (note: -c postgres is required with -t):
dave test -c postgres -t iso3166 -t dellstore
```

To (re)generate an expected file after an intentional dataset change, run the
script in update mode against a freshly built image:

```sh
test/integration/run.sh --update iso3166 iso3166   # <tag> <datasets-csv>
```

CI runs all three commands; see `.github/workflows/ci.yml`.

[cst]: https://github.com/GoogleContainerTools/container-structure-test

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

## Future Work

* More MySQL datasets: port additional PostgreSQL datasets where a MySQL-native source exists or the upstream is format-neutral enough to hand-translate faithfully (see [Datasets not ported to MySQL](#datasets-not-ported-to-mysql)).
* [ClickHouse](https://clickhouse.com/) images: ship the same sample datasets on ClickHouse — an OLAP columnar engine whose SQL dialect and bulk-load model (`MergeTree`, `INSERT`/`CSV`) differ from PostgreSQL enough that most datasets would need engine-specific transforms rather than reusing the postgres dumps verbatim.
* [DuckDB](https://duckdb.org/) images: ship the same sample datasets on DuckDB — an embedded analytical database (like SQLite, a database file rather than a server to boot) with strong PostgreSQL compatibility for many plain DDL + data dumps, so several datasets may port with little change.
* [Apache Druid](https://druid.apache.org/) images: ship the same sample datasets on Druid — a real-time OLAP datastore built around immutable segments and batch/stream ingestion rather than conventional DDL + `INSERT`/`COPY`, so each dataset would need a dedicated ingest pipeline and schema mapping.
* [Apache Pinot](https://pinot.apache.org/) images: ship the same sample datasets on Pinot — a distributed OLAP engine oriented toward star-schema analytics tables and offline/online ingestion jobs, so the relational sample dumps would need similar per-dataset transforms and load paths rather than loading postgres SQL as-is.
* Find and add more free data sources.
