# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

**Pre-populated sample databases as Docker images** — ready-to-run [PostgreSQL](https://www.postgresql.org/), [MySQL](https://www.mysql.com/), [CockroachDB](https://www.cockroachlabs.com/), and [SQLite](https://www.sqlite.org/) containers loaded with real, valid sample data (Chinook, Northwind, Sakila/Pagila, World, AdventureWorks, Stack Exchange, and more). Ever needed a database already populated with valid data — to practice SQL, run tests, demo an app, or benchmark — without hand-crafting rows or hunting for a usable dump? Every image ships exactly one dataset in its own database, so you just `docker run` and connect.

## Dataset support matrix

Each cell is the image tag to pull for that dataset on that engine; **—** means it isn't shipped there (yet). The dataset name links to its upstream source when every engine pulls from the same one; where engines use different upstreams, the source link is on the individual tag instead. All images are published for `linux/amd64` and `linux/arm64`.

| Dataset | [PostgreSQL](postgres/README.md) | [MySQL](mysql/README.md) | [CockroachDB](cockroach/README.md) | [SQLite](sqlite/README.md) |
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

[ClickHouse](https://clickhouse.com/), [DuckDB](https://duckdb.org/), [Apache Druid](https://druid.apache.org/), and [Apache Pinot](https://pinot.apache.org/) are planned — see [Future Work](#future-work).

## Quick start

```
docker run -d --name pg-ds-world aa8y/postgres-dataset:world
docker exec -it pg-ds-world psql -d world
```

Each engine's README has the equivalent client invocation and per-dataset notes: [PostgreSQL](postgres/README.md), [MySQL](mysql/README.md), [CockroachDB](cockroach/README.md), [SQLite](sqlite/README.md).

## Tag naming

The database inside each image is the bare dataset name — the tag minus any `yugabyte-`/`stackexchange-` prefix (e.g. `yugabyte-chinook` → `chinook`, `stackexchange-beer` → `beer`). Source prefixes exist so a dataset could ship from a second mirror later; `sportsdb` and `yugabyte-sportsdb` are the same image today, with the unprefixed `sportsdb` kept as a backwards-compatible alias.

## Documentation

* Engine guides: [PostgreSQL](postgres/README.md) · [MySQL](mysql/README.md) · [CockroachDB](cockroach/README.md) · [SQLite](sqlite/README.md)
* [Building images](docs/building.md) — `dave`, custom images, and build caching
* [Testing](docs/testing.md) — structure tests and integration smoke tests
* [Dataset attribution and licenses](docs/ATTRIBUTION.md)

Docker Hub repositories: [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) · [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset) · [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset) · [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset)

## Dataset licenses

This repository's own software and packaging are [MIT licensed](LICENSE). Each bundled dataset keeps its upstream license — see [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md) for the per-dataset sources, licenses, and required attributions (notably the Stack Exchange dumps, which are CC BY-SA 4.0).

## Future Work

* More MySQL datasets: port additional PostgreSQL datasets where a MySQL-native source exists or the upstream is format-neutral enough to hand-translate faithfully (see [Datasets not ported to MySQL](mysql/README.md#datasets-not-ported-to-mysql)).
* [ClickHouse](https://clickhouse.com/) images: an OLAP columnar engine whose SQL dialect and bulk-load model (`MergeTree`, `INSERT`/`CSV`) differ from PostgreSQL enough that most datasets would need engine-specific transforms rather than reusing the postgres dumps verbatim.
* [DuckDB](https://duckdb.org/) images: an embedded analytical database (like SQLite, a database file rather than a server to boot) with strong PostgreSQL compatibility for plain DDL + data dumps, so several datasets may port with little change.
* [Apache Druid](https://druid.apache.org/) images: a real-time OLAP datastore built around immutable segments and batch/stream ingestion rather than conventional DDL + `INSERT`/`COPY`, so each dataset would need a dedicated ingest pipeline and schema mapping.
* [Apache Pinot](https://pinot.apache.org/) images: a distributed OLAP engine oriented toward star-schema analytics tables and offline/online ingestion jobs, so the relational sample dumps would need similar per-dataset transforms and load paths.
* Find and add more free data sources.
