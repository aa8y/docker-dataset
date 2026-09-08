# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

**Pre-populated sample databases as Docker images** — ready-to-run [PostgreSQL](https://www.postgresql.org/), [MySQL](https://www.mysql.com/), [CockroachDB](https://www.cockroachlabs.com/), [SQLite](https://www.sqlite.org/), [DuckDB](https://duckdb.org/), [ClickHouse](https://clickhouse.com/), [Apache Druid](https://druid.apache.org/), and [Apache Pinot](https://pinot.apache.org/) containers loaded with real, valid sample data (Chinook, Northwind, Sakila/Pagila, World, AdventureWorks, Stack Exchange, and more). Ever needed a database already populated with valid data — to practice SQL, run tests, demo an app, or benchmark — without hand-crafting rows or hunting for a usable dump? Every image ships exactly one dataset in its own database, so you just `docker run` and connect.

## Dataset support matrix

Each cell is the image tag to pull for that dataset on that engine; **—** means it isn't shipped there (yet). The dataset name links to its upstream source when every engine pulls from the same one; where engines use different upstreams, the source link is on the individual tag instead. All images are published for `linux/amd64` and `linux/arm64`.

| Dataset | [PostgreSQL](postgres/README.md) | [MySQL](mysql/README.md) | [CockroachDB](cockroach/README.md) | [SQLite](sqlite/README.md) | [DuckDB](duckdb/README.md) | [ClickHouse](clickhouse/README.md) | [Apache Druid](druid/README.md) | [Apache Pinot](pinot/README.md) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [AdventureWorks](https://github.com/lorint/AdventureWorks-for-Postgres) | `adventureworks` | — | — | — | — | — | — | — |
| [Airlines](https://postgrespro.com/education/demodb) | `airlines` | — | — | `airlines` | `airlines` | — | — | — |
| Chinook | [`yugabyte-chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | — | — |
| [Dell DVD Store](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` | `dellstore` |
| [Employees](https://github.com/datacharmer/test_db) | `employees` | `employees` | `employees` | `employees` | `employees` | — | — | — |
| [French Towns](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` |
| [GeoNames](https://download.geonames.org/export/dump/) | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` | `geonames` |
| [ISO 3166](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` | `iso3166` |
| [MoMA](https://github.com/MuseumofModernArt/collection) | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` | `moma` |
| Northwind | [`yugabyte-northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/dalers/mywind) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/jpwhite3/northwind-SQLite3) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | — | — | — |
| [NYC Taxi Trip Records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | — | — | — | — | `nyc-taxi` | `nyc-taxi` | — | — |
| [OMDb](https://github.com/df7cb/omdb-postgresql) | `omdb` | — | — | — | — | — | — | — |
| [OpenFlights](https://github.com/jpatokal/openflights/tree/master/data) | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` | `openflights` |
| [PGExercises](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `yugabyte-pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` |
| Sakila / Pagila | [`pagila`](https://github.com/devrimgunduz/pagila) | [`sakila`](https://dev.mysql.com/doc/sakila/en/) | [`sakila`](https://github.com/jOOQ/sakila) | [`sakila`](https://github.com/bradleygrant/sakila-sqlite3) | [`sakila`](https://github.com/jOOQ/sakila) | — | — | — |
| [SportsDB](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `sportsdb`, `yugabyte-sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` | — | — | — |
| [Stack Exchange](https://archive.org/details/stackexchange)¹ | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | — | — |
| [USDA](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` | `usda` |
| World | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://dev.mysql.com/doc/world-setup/en/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) |

¹ `<site>` is one of `beer`, `coffee`, `poker`, `woodworking`, `chess`, `cooking`, `outdoors`, `boardgames` (e.g. `stackexchange-chess`).

Every engine also publishes a `latest` tag: it tracks `world` on PostgreSQL, MySQL, Apache Druid, and Apache Pinot, `chinook` on CockroachDB, SQLite, and DuckDB, and `nyc-taxi` on ClickHouse.

## Quick start

```
docker run -d --name pg-ds-world aa8y/postgres-dataset:world
docker exec -it pg-ds-world psql -d world
```

Each engine's README has the equivalent client invocation and per-dataset notes: [PostgreSQL](postgres/README.md), [MySQL](mysql/README.md), [CockroachDB](cockroach/README.md), [SQLite](sqlite/README.md), [DuckDB](duckdb/README.md), [ClickHouse](clickhouse/README.md), [Apache Druid](druid/README.md), [Apache Pinot](pinot/README.md).

## Tag naming

The database inside each image is the bare dataset name — the tag minus any `yugabyte-`/`stackexchange-` prefix (e.g. `yugabyte-chinook` → `chinook`, `stackexchange-beer` → `beer`). Source prefixes exist so a dataset could ship from a second mirror later; `sportsdb` and `yugabyte-sportsdb` are the same image today, with the unprefixed `sportsdb` kept as a backwards-compatible alias. One exception: on ClickHouse the `nyc-taxi` tag's database is `nyc_taxi`, because the base image interpolates the name into SQL unquoted and a hyphen does not survive that.

## Documentation

* Engine guides: [PostgreSQL](postgres/README.md) · [MySQL](mysql/README.md) · [CockroachDB](cockroach/README.md) · [SQLite](sqlite/README.md) · [DuckDB](duckdb/README.md) · [ClickHouse](clickhouse/README.md) · [Apache Druid](druid/README.md) · [Apache Pinot](pinot/README.md)
* [Building images](docs/building.md) — `dave`, custom images, and build caching
* [Testing](docs/testing.md) — structure tests and integration smoke tests
* [Dataset attribution and licenses](docs/ATTRIBUTION.md)

Docker Hub repositories: [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) · [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset) · [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset) · [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset) · [`aa8y/duckdb-dataset`](https://hub.docker.com/r/aa8y/duckdb-dataset) · [`aa8y/clickhouse-dataset`](https://hub.docker.com/r/aa8y/clickhouse-dataset) · [`aa8y/druid-dataset`](https://hub.docker.com/r/aa8y/druid-dataset) · [`aa8y/pinot-dataset`](https://hub.docker.com/r/aa8y/pinot-dataset)

## Dataset licenses

This repository's own software and packaging are [MIT licensed](LICENSE). Each bundled dataset keeps its upstream license — see [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md) for the per-dataset sources, licenses, and required attributions (notably the Stack Exchange dumps, which are CC BY-SA 4.0).

## Future Work

* The last matrix gaps. `adventureworks` and `omdb` stay PostgreSQL-only by design (their upstreams lean on PostgreSQL-specific machinery — see [Datasets not ported to MySQL](mysql/README.md#datasets-not-ported-to-mysql)). `nyc-taxi` is Parquet, which only DuckDB reads natively; the other engines would need a Parquet-to-CSV stage in every Dockerfile and a ~500 MB CSV shipped in each image. `airlines` on MySQL and CockroachDB is a volume problem, not a dialect one: 10.7M rows replayed as init-time `INSERT`s would blow the smoke test's readiness budget, so it needs a bulk-load path first (MariaDB's `LOAD DATA INFILE`, CockroachDB's `IMPORT INTO` as the `employees` tag already does) and a ~500 MB data payload in the image.
* More ClickHouse datasets: the engine carries the pgFoundry family, `chinook`, `nyc-taxi`, the CSV datasets and the Stack Exchange sites; the remaining gaps need per-dataset work (`northwind`'s `bytea` columns, `sportsdb`'s 107 mostly-empty tables) — see [Datasets not ported to ClickHouse](clickhouse/README.md#datasets-not-ported-to-clickhouse).
* More DuckDB datasets: the engine now carries every dataset except `adventureworks` and `omdb` (see [duckdb/README.md](duckdb/README.md#duckdb-datasets)), so new additions here are about new sources rather than porting.
* More Apache Druid datasets: the engine carries the pgFoundry family, `pgexercises`, `geonames`, `openflights` and `moma`; the gaps need either an input format that tolerates embedded newlines (the Stack Exchange sites) or per-tag JVM sizing (`nyc-taxi` ingests in under two minutes with a 1 GB peon, but the shared nano profile gives it 256 MB) — see [Datasets not ported to Druid](druid/README.md#datasets-not-ported-to-druid).
* More Apache Pinot datasets: `nyc-taxi` is the obvious next tag — a single wide fact table with a real time column, which needs Pinot's Parquet ingestion job rather than the controller's synchronous CSV endpoint the current tags use — see [Datasets not ported to Pinot](pinot/README.md#datasets-not-ported-to-pinot).
* More Parquet-native datasets: `nyc-taxi` showed the shape (fetch a Parquet file, `CREATE TABLE ... AS FROM read_parquet(...)`), and the open-data world publishes plenty more.
* Find and add more free data sources.
