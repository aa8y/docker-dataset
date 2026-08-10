# MySQL images — `aa8y/mysql-dataset`

The MySQL images mirror the PostgreSQL ones — one dataset per image, same ETL [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml). The engine is MariaDB (see [Base image](#base-image) for why); it is wire- and SQL-compatible with MySQL for these samples. Because each image is a single dataset, the build strips any database-level DDL the upstream dump ships (`CREATE`/`DROP DATABASE`/`SCHEMA`, `USE`) and loads everything into one database named after the dataset.

The available tags are the MySQL column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[MySQL](https://www.mysql.com/) as [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset). There is no official Alpine image for Oracle MySQL (the official `mysql` image is Oracle Linux / Debian based) and Alpine's own package repositories ship [MariaDB](https://mariadb.org/) in place of MySQL, so to keep the "thin, Alpine-based" goal we build on the community [`yobasystems/alpine-mariadb`](https://hub.docker.com/r/yobasystems/alpine-mariadb) image. MariaDB is the MySQL drop-in Alpine substitutes, and its entrypoint honours the same `MYSQL_*` env vars and `/docker-entrypoint-initdb.d/*.sql` convention as the official postgres image, so the dataset pattern carries over unchanged.

## Usage

Start a container and connect with the `mariadb` (MySQL-compatible) client:
```
docker run -d --name my-ds-<tag> aa8y/mysql-dataset:<tag>
docker exec -it my-ds-<tag> mariadb -uroot -pmysql <db_name>
```
where `<tag>` is one of the tags in the MySQL column of the [matrix](../README.md#dataset-support-matrix) and `<db_name>` is the matching dataset name (the tag itself, minus any `stackexchange-` prefix). The root password is `mysql`.

## MySQL datasets

MySQL-native sources, used directly (sources in the [matrix](../README.md#dataset-support-matrix); notes below are MySQL-specific):

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

## Datasets not ported to MySQL

The remaining PostgreSQL datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features (PL/pgSQL, extensions, `pg_dump` internals) that can't be hand-translated without diverging from the upstream dataset. Plain DDL + data dumps are instead hand-translated (see the group above); these are the ones that remain PostgreSQL-only:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL, and MySQL uses the original Sakila directly (tag `sakila`, above).
* `adventureworks`: the only maintained open port ([lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres)) targets PostgreSQL. AdventureWorks is a Microsoft SQL Server sample with no comparable, maintained MySQL port, and its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to hand-translate faithfully.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows); it is PostgreSQL-only.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) is PostgreSQL-specific — its views rely on the `tsm_system_rows` extension (no MySQL equivalent), so a port would have to drop them and would no longer be the upstream dataset.
* `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-sportsdb`: superseded on MySQL by the native/ported `chinook`, `northwind`, and `sportsdb` tags above (the Yugabyte SQL is PostgreSQL dialect; `sportsdb` is hand-translated from the same dump, so the prefixed tag is not duplicated here).

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c mysql -t dellstore
```

To add or change a MySQL dataset, declare its `extractUrl`, `sqlFiles` and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
