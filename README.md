# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

**Pre-populated sample databases as Docker images** — ready-to-run [PostgreSQL](https://www.postgresql.org/), [MySQL](https://www.mysql.com/), [CockroachDB](https://www.cockroachlabs.com/), [SQLite](https://www.sqlite.org/), [DuckDB](https://duckdb.org/), [ClickHouse](https://clickhouse.com/), [Apache Druid](https://druid.apache.org/), and [Apache Pinot](https://pinot.apache.org/) containers loaded with real, valid sample data (Chinook, Northwind, Sakila/Pagila, World, AdventureWorks, Stack Exchange, and more). Ever needed a database already populated with valid data — to practice SQL, run tests, demo an app, or benchmark — without hand-crafting rows or hunting for a usable dump? Every image ships exactly one dataset, so you just `docker run` and connect.

## Quick start

Run the PostgreSQL `world` image, wait for it to initialize, run a real query, and clean up:

```
docker run -d --name pg-ds-world aa8y/postgres-dataset:world
# The first start loads the dataset; give it a few seconds. Watch for the
# second "database system is ready to accept connections":
docker logs -f pg-ds-world
docker exec -it pg-ds-world psql -d world -c 'SELECT name, population FROM city ORDER BY population DESC LIMIT 5'
docker rm -f pg-ds-world
```

That is the whole shape of it: pull a tag from the [matrix](#dataset-support-matrix) below, `docker run`, connect. Each engine connects a little differently (server engines take a client over a port; SQLite and DuckDB open a file), and each has per-dataset notes — see its guide: [PostgreSQL](postgres/README.md) · [MySQL](mysql/README.md) · [CockroachDB](cockroach/README.md) · [SQLite](sqlite/README.md) · [DuckDB](duckdb/README.md) · [ClickHouse](clickhouse/README.md) · [Apache Druid](druid/README.md) · [Apache Pinot](pinot/README.md).

## Dataset support matrix

Each cell is the image tag to pull for that dataset on that engine; **—** means it isn't shipped there (yet). The dataset name links to its upstream source when every engine pulls from the same one; where engines use different upstreams, the source link is on the individual tag instead. All images are published for `linux/amd64` and `linux/arm64`.

| Dataset | [PostgreSQL](postgres/README.md) | [MySQL](mysql/README.md) | [CockroachDB](cockroach/README.md) | [SQLite](sqlite/README.md) | [DuckDB](duckdb/README.md) | [ClickHouse](clickhouse/README.md) | [Apache Druid](druid/README.md) | [Apache Pinot](pinot/README.md) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [AdventureWorks](https://github.com/lorint/AdventureWorks-for-Postgres) | `adventureworks` | — | — | — | — | — | — | — |
| [Airlines](https://postgrespro.com/education/demodb) | `airlines` | — | — | `airlines` | `airlines` | — | — | — |
| Chinook | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | — | — |
| [Dell DVD Store](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` |
| [Employees](https://github.com/datacharmer/test_db) | `employees` | `employees` | `employees` | `employees` | `employees` | — | — | — |
| [French Towns](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` |
| [GeoNames](https://download.geonames.org/export/dump/) | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` |
| [ISO 3166](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` |
| [MoMA](https://github.com/MuseumofModernArt/collection) | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` |
| Northwind | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/dalers/mywind) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/jpwhite3/northwind-SQLite3) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | — | — | — |
| [NYC Taxi Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | — | — | — | — | `nyc-taxi` | `nyc-taxi` | — | — |
| [OMDb](https://github.com/df7cb/omdb-postgresql) | `omdb` | — | — | — | — | — | — | — |
| [OpenFlights](https://github.com/jpatokal/openflights/tree/master/data) | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` |
| [PGExercises](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` |
| Sakila / Pagila | [`pagila`](https://github.com/devrimgunduz/pagila) | [`sakila`](https://dev.mysql.com/doc/sakila/en/) | [`sakila`](https://github.com/jOOQ/sakila) | [`sakila`](https://github.com/bradleygrant/sakila-sqlite3) | [`sakila`](https://github.com/jOOQ/sakila) | — | — | — |
| [SportsDB](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` | — | — | — |
| [Stack Exchange](https://archive.org/details/stackexchange)¹ | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | — | — |
| [USDA](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` |
| World | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://dev.mysql.com/doc/world-setup/en/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) |

¹ `<site>` is one of `beer`, `coffee`, `poker`, `woodworking`, `chess`, `cooking`, `outdoors`, `boardgames` (e.g. `stackexchange-chess`).

Every engine also publishes a `latest` tag. It is an **alias**, not a dataset of its own: it opens the same dataset one of the named tags does — `world` on PostgreSQL, MySQL, Apache Druid, and Apache Pinot; `chinook` on CockroachDB, SQLite, and DuckDB; and `nyc-taxi` on ClickHouse.

## Tag naming

A tag names the dataset an image carries. How that dataset is addressed once the container is up depends on the engine:

* **PostgreSQL, MySQL, CockroachDB, SQLite, DuckDB, ClickHouse** put the dataset in a **named database** (or, for SQLite/DuckDB, a named file). The name is the tag minus any `stackexchange-` prefix (e.g. `stackexchange-beer` → `beer`). Two things are not databases named after the tag: the `latest` alias opens its target dataset's database (e.g. `world`, not `latest`), and on ClickHouse the `nyc-taxi` tag's database is `nyc_taxi`, because the base image interpolates the name into SQL unquoted and a hyphen does not survive that.
* **Apache Druid and Apache Pinot** have no per-dataset database to name — Druid exposes the dataset's tables as datasources in its single `druid` schema, and Pinot as a flat namespace of tables — so you query the tables directly. Each engine's guide shows how.

## Documentation

* Engine guides: [PostgreSQL](postgres/README.md) · [MySQL](mysql/README.md) · [CockroachDB](cockroach/README.md) · [SQLite](sqlite/README.md) · [DuckDB](duckdb/README.md) · [ClickHouse](clickhouse/README.md) · [Apache Druid](druid/README.md) · [Apache Pinot](pinot/README.md) — each has the client invocation, host-connection details, and per-dataset notes for its engine.
* [Building images](docs/building.md) — `dave`, custom images, and build caching
* [Testing](docs/testing.md) — structure tests and integration smoke tests
* [Dataset attribution and licenses](docs/ATTRIBUTION.md)

Docker Hub repositories: [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) · [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset) · [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset) · [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset) · [`aa8y/duckdb-dataset`](https://hub.docker.com/r/aa8y/duckdb-dataset) · [`aa8y/clickhouse-dataset`](https://hub.docker.com/r/aa8y/clickhouse-dataset) · [`aa8y/druid-dataset`](https://hub.docker.com/r/aa8y/druid-dataset) · [`aa8y/pinot-dataset`](https://hub.docker.com/r/aa8y/pinot-dataset)

## Dataset licenses

This repository's own software and packaging are [MIT licensed](LICENSE). Each bundled dataset keeps its upstream license — see [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md) for the per-dataset sources, licenses, and required attributions (notably the Stack Exchange dumps, which are CC BY-SA 4.0).

## Future Work

The remaining matrix gaps, and what each one is waiting on:

* **The last matrix gaps.** `adventureworks` and `omdb` stay PostgreSQL-only by design (their upstreams lean on PostgreSQL-specific machinery — see [Datasets not ported to MySQL](mysql/README.md#datasets-not-ported-to-mysql)). `airlines` on MySQL and CockroachDB is a volume problem, not a dialect one: 10.7M rows replayed as init-time `INSERT`s would blow the smoke test's readiness budget, so it needs a bulk-load path first (MariaDB's `LOAD DATA INFILE`, CockroachDB's `IMPORT INTO` as the `employees` tag already does) and a ~500 MB data payload in the image.
* **More OLAP datasets.** ClickHouse carries the pgFoundry family, `chinook`, `nyc-taxi`, the CSV datasets and the Stack Exchange sites; its remaining gaps need per-dataset work (`northwind`'s `bytea` columns, `sportsdb`'s 107 mostly-empty tables — see [Datasets not ported to ClickHouse](clickhouse/README.md#datasets-not-ported-to-clickhouse)). Druid needs an input format that tolerates embedded newlines (the Stack Exchange sites) or per-tag JVM sizing (`nyc-taxi`) — see [Datasets not ported to Druid](druid/README.md#datasets-not-ported-to-druid). Pinot's obvious next tag is `nyc-taxi`, which needs its Parquet ingestion job rather than the controller's synchronous CSV endpoint — see [Datasets not ported to Pinot](pinot/README.md#datasets-not-ported-to-pinot).
* **More Parquet-native datasets.** DuckDB and ClickHouse both ship `nyc-taxi` from Parquet already (DuckDB reads it at build time; ClickHouse loads it at container start), and the open-data world publishes plenty more sources in that shape.
* **More free data sources** across every engine.
