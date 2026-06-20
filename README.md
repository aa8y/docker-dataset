# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

Have you ever wanted to access pre-populated databases with dummy but valid data? It can be for something as simple as practicing writing SQL queries to running tests on databases. Under such circumstances, you have to either have to create dummy data or utilize some internet-searching skills to find data to populate your database. I think this is a common enough problem/requirement that solution can be Dockerized for reuse. So here is a Docker image for [PostgreSQL](https://www.postgresql.org/) with databases populated with sample data.

## Datasets

So far we have the following datasets which are being used in the images.
* [Postgres Sample Databases](https://wiki.postgresql.org/wiki/Sample_Databases): The datasets being used from here are `dellstore2` (tagged `dellstore`), `french-towns-communes-francaises` (tagged `frenchtowns`), `iso3166`, `usda` and `world`, all sourced from PostgreSQL's FTP mirror of [pgFoundry dbsamples](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/).
* `sportsdb`: the original `www.sportsdb.org` download is no longer available, so we use the mirror Yugabyte ships in [its sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample). This mirror defines all 107 sportsdb tables but only populates data for the generic infrastructure tables (events, persons, teams, seasons, etc.) plus american football, baseball, basketball, and ice hockey stats. Motor racing, soccer, tennis, wagering, and weather tables are schema-only.
* `chinook` (tagged `yugabyte-chinook`): a digital media store — artists, albums, tracks, customers, and invoices (11 tables in the `public` schema). Sourced from [Yugabyte's sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample); tables use quoted CamelCase identifiers (e.g. `"Track"`, `"InvoiceLine"`).
* `northwind` (tagged `yugabyte-northwind`): the classic Northwind specialty-foods import/export company — customers, orders, products, employees, and suppliers (14 tables in the `public` schema). Sourced from [Yugabyte's sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample).
* `pgexercises` (tagged `yugabyte-pgexercises`): the "clubdata" database behind [pgexercises.com](https://pgexercises.com/) — a country club's members, bookable facilities, and bookings (3 tables in a dedicated `cd` schema, not `public`). Sourced from [Yugabyte's sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample).
* `pagila`: the classic Sakila/"DVD rental store" sample ported to Postgres — films, actors, customers, inventory, rentals, and payments. We source it from [devrimgunduz/pagila](https://github.com/devrimgunduz/pagila), a maintained fork (pgFoundry's original no longer loads on modern Postgres). Its `payment` table is range-partitioned by month (`payment_p2022_NN`), so row counts are split across the parent and its partitions. Note: the upstream maintainer periodically shifts the data's dates to the then-current year, so absolute dates in the sample may differ between rebuilds.
* `omdb`: the [Open Media Database](https://www.omdb.org/) film catalogue, packaged for Postgres at [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql). CSV data is fetched from `www.omdb.org` at build time and shipped inside the image so `\copy` resolves at container start. The init script also creates the `tsm_system_rows` extension that the upstream views rely on. Heads up: this dataset is much larger than the others (~150 MB of CSV + indexes), which makes the `omdb` image noticeably heavier.
* `adventureworks`: the Microsoft AdventureWorks 2014 OLTP sample (a fictitious bicycle parts wholesaler — 68 tables, 5 schemas, ~300 employees, 500 products, 20k customers, 31k sales). We use the [lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres) port, which pulls Microsoft's CSV bundle and runs a Python reformat before loading. CSVs ship alongside the init script so the upstream `\copy ./X.csv` directives resolve at container start. This dataset is also on the heavier side (~90 MB of CSV).
* `airlines`: the [postgrespro "airlines" demo database](https://postgrespro.com/education/demodb) — a flight-booking model (airports, flights, tickets, bookings, boarding passes, seats; 9 tables in a `bookings` schema, with `search_path` defaulting to it). We ship the smallest ("3 months") English snapshot. Upstream distributes it as a single gzipped `pg_dump` that manages its own `demo` database, so the build decompresses it and strips the `DROP/CREATE DATABASE demo` / `\connect` directives (retargeting the `ALTER DATABASE` options) so it loads into the `airlines` database. Heads up: this is the largest dataset — the dump inlines several million rows (boarding passes, segments, tickets), so the image is heavy. The snapshot URL is date-stamped, so it may need bumping if postgrespro retires the pinned file.
* `moma`: the [Museum of Modern Art research collection](https://github.com/MuseumofModernArt/collection) — ~160k catalogued artworks and ~16k artists (2 tables in the `public` schema). MoMA publishes only CSV/JSON (no SQL), so the schema is authored in-repo (`postgres/scripts/moma/schema.sql`, every column `text` since the data is free-form) and the CSVs ship alongside the init script so `\copy` resolves at container start. Note: MoMA refreshes the published CSVs periodically, so exact row counts drift over time.
* **Stack Exchange sites** (tagged `stackexchange-<site>`): Q&A site dumps — posts, comments, users, votes, badges, tags, post links, and post history (8 tables in the `public` schema). Each is sourced from the [Stack Exchange data dump on archive.org](https://archive.org/details/stackexchange), which ships only per-table XML. Adapting the schema, column mapping, and indexes from [stackexchange-dump-to-postgres](https://github.com/Human-Centric-Machine-Learning/stackexchange-dump-to-postgres), a shared build hook (`postgres/scripts/stackexchange/transform`) converts the XML into SQL — `CREATE TABLE` + inline `COPY` + indexes — rather than running the upstream importer against a live server, which keeps the dataset within our extract/transform/load build (no database running at build time). Every Stack Exchange site shares one schema, so they all build through that single hook (each site's `postgres/scripts/<site>` directory is a symlink to `postgres/scripts/stackexchange`); adding a site is just a tag in `manifest.yml`, a structure-test config, and an expected-counts file. Unknown attributes from newer dumps are ignored, and since the upstream dumps are refreshed periodically, counts are recorded as floors. The sites currently shipped (database name in parentheses):
  * [Beer](https://beer.stackexchange.com/) — `stackexchange-beer` (db `beer`)
  * [Coffee](https://coffee.stackexchange.com/) — `stackexchange-coffee` (db `coffee`)
  * [Poker](https://poker.stackexchange.com/) — `stackexchange-poker` (db `poker`)
  * [Woodworking](https://woodworking.stackexchange.com/) — `stackexchange-woodworking` (db `woodworking`)
  * [Chess](https://chess.stackexchange.com/) — `stackexchange-chess` (db `chess`)
  * [Seasoned Advice (Cooking)](https://cooking.stackexchange.com/) — `stackexchange-cooking` (db `cooking`). This is the largest Stack Exchange image we ship (~500k votes, ~230k post-history rows); the others are comparatively light.

## Databases

Two database engines are supported, each published as its own image repository:

* [PostgreSQL](https://www.postgresql.org/) as [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset). We use the `alpine` version of the official image as the base image to keep our image slim.
* [MySQL](https://www.mysql.com/) as [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset). There is no official Alpine image for Oracle MySQL (the official `mysql` image is Oracle Linux / Debian based) and Alpine's own package repositories ship [MariaDB](https://mariadb.org/) in place of MySQL, so to keep the "thin, Alpine-based" goal we build on the community [`yobasystems/alpine-mariadb`](https://hub.docker.com/r/yobasystems/alpine-mariadb) image. MariaDB is the MySQL drop-in Alpine substitutes, and its entrypoint honours the same `MYSQL_*` env vars and `/docker-entrypoint-initdb.d/*.sql` convention as the official postgres image, so the dataset pattern carries over unchanged. See [MySQL images](#mysql-images) for the datasets and tags available.

## Tags

Available tags are `adventureworks`, `airlines`, `dellstore`, `frenchtowns`, `iso3166`, `moma`, `omdb`, `pagila`, `stackexchange-beer`, `stackexchange-coffee`, `stackexchange-poker`, `stackexchange-woodworking`, `stackexchange-chess`, `stackexchange-cooking`, `sportsdb`, `yugabyte-sportsdb`, `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-pgexercises`, `usda`, `world` and `latest`. Each image carries exactly one dataset, loaded into its own database. `latest` currently tracks the `world` dataset. All tags are published for `linux/amd64` and `linux/arm64`.

`sportsdb` and `yugabyte-sportsdb` are currently the same image — the only mirror we ship is Yugabyte's. `sportsdb` is a special case: it predates the mirror-explicit naming, so we keep the bare `sportsdb` tag working for backwards compatibility while `yugabyte-sportsdb` exists so that if we add another sportsdb mirror later (e.g. a hypothetical `pgfoundry-sportsdb`), users can pin to the specific source they want and `sportsdb` continues to track whichever mirror is the current default.

The other Yugabyte-sourced datasets — `chinook`, `northwind`, and `pgexercises` — have no legacy bare tags to preserve, so they ship under their `yugabyte-`prefixed tags only (`yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-pgexercises`). The database name inside each image is still the bare dataset name (`chinook`, `northwind`, `pgexercises`). If we ever add a second mirror for one of these, the prefixed tag already disambiguates the source.

Stack Exchange is a family of sites rather than a single dataset, so — like the `yugabyte-` tags — each tag carries the source-and-site prefix: `stackexchange-beer`, `stackexchange-coffee`, `stackexchange-poker`, `stackexchange-woodworking`, `stackexchange-chess`, `stackexchange-cooking`. The database inside each is the bare site name (`beer`, `coffee`, `poker`, `woodworking`, `chess`, `cooking`). Because every Stack Exchange dump shares one schema, all sites build through the same shared hook (`postgres/scripts/stackexchange`), so adding another site is just another `stackexchange-<site>` tag.

### `all` has been retired

The multi-dataset `all` tag (and the all-datasets `latest`) is legacy: images are now one dataset each. If you need several datasets together, run one container per dataset (e.g. via `docker-compose`), or build a custom image per dataset.

### `pagila` was removed and re-added

`pagila` was [removed in 2019](https://github.com/aa8y/docker-dataset/issues/1) because the upstream source shipped a change that wouldn't load on any Postgres version, which back then also took down the combined `all`/`latest` images. Both causes are now gone: the [upstream fork](https://github.com/devrimgunduz/pagila) loads cleanly on modern Postgres (tested against 12+), and images are now one dataset each, so a single dataset can no longer break the others. It is therefore back as a regular tag.

## MySQL images

The MySQL images mirror the PostgreSQL ones: each [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset) image carries exactly one dataset, loaded into its own database, and is built through the same Extract -> Transform -> Load [Dockerfile](mysql/Dockerfile) driven by `manifest.yml`. The engine is MariaDB (see [Databases](#databases) for why); it is wire- and SQL-compatible with MySQL for these samples. Because each image is a single dataset, the build strips any database-level DDL the upstream dump ships (`CREATE`/`DROP DATABASE`/`SCHEMA`, `USE`) and loads everything into one database named after the dataset. All MySQL tags are published for `linux/amd64` and `linux/arm64`.

Where a dataset has a MySQL-native source we use it directly; the canonical Sakila sample (tagged `sakila`) takes the place of PostgreSQL's `pagila`, which is itself a port of Sakila.

Start a container and connect with the `mariadb` (MySQL-compatible) client:
```
docker run -d --name my-ds-<tag> aa8y/mysql-dataset:<tag>
docker exec -it my-ds-<tag> mariadb -uroot -pmysql <db_name>
```
where `<tag>` is one of the MySQL tags below and `<db_name>` is the matching dataset name. The root password is `mysql`.

### MySQL datasets

* `sakila`: MySQL's own [Sakila sample database](https://dev.mysql.com/doc/sakila/en/) — the canonical "DVD rental store" model (films, actors, customers, inventory, rentals, and payments; 16 base tables in the `sakila` database). This is the original that PostgreSQL's `pagila` ports, so it stands in for `pagila` on MySQL. We source the official `sakila-db.tar.gz` (`sakila-schema.sql` + `sakila-data.sql`). Note: `film_text` is populated by an `AFTER INSERT` trigger on `film` rather than by bulk data, and unlike `pagila` the `payment` table is not partitioned.
* `world`: MySQL's canonical [world sample database](https://dev.mysql.com/doc/world-setup/en/) — `city`, `country`, and `countrylanguage` (3 tables in the `world` database). These are the same three tables as the PostgreSQL `world` dataset, with identical row counts. Sourced from the official `world-db.tar.gz`.
* `chinook`: the [Chinook](https://github.com/lerocha/chinook-database) digital media store — artists, albums, tracks, customers, and invoices (11 tables in the `chinook` database). We use the vendor's MySQL-specific `Chinook_MySql.sql` (release `v1.4.5`); like the PostgreSQL `yugabyte-chinook` tag, tables use quoted CamelCase identifiers (e.g. `` `Track` ``, `` `InvoiceLine` ``). The upstream script's own `CREATE DATABASE Chinook` is stripped so it loads into the lowercase `chinook` database.
* `northwind`: the classic Northwind specialty-foods import/export company — customers, orders, products, employees, and suppliers (20 tables in the `northwind` database). MySQL has no first-party Northwind, so we use the well-established [dalers/mywind](https://github.com/dalers/mywind) port of Microsoft's Access Northwind sample (snake_case identifiers; its table DDL is schema-qualified to `northwind`). Note this is a larger 20-table conversion of the Access database rather than the 14-table model behind the PostgreSQL `yugabyte-northwind` tag.
* `moma`: the [Museum of Modern Art research collection](https://github.com/MuseumofModernArt/collection) — ~160k catalogued artworks and ~16k artists (2 tables in the `moma` database). As on the PostgreSQL side, MoMA publishes only CSV/JSON (no SQL), so the schema is authored in-repo (`mysql/scripts/moma/schema.sql`, every column `text` since the data is free-form) and the CSVs ship alongside the init script. The data is bulk-loaded at container start with server-side `LOAD DATA INFILE`. Note: MoMA refreshes the published CSVs periodically, so exact row counts drift over time (the smoke test records them as floors).
* **Stack Exchange sites** (tagged `stackexchange-<site>`): the same Q&A site dumps as the PostgreSQL family — posts, comments, users, votes, badges, tags, post links, and post history (8 tables, identifiers in CamelCase, e.g. `` `Posts` ``, `` `PostHistory` ``). Each is sourced from the [Stack Exchange data dump on archive.org](https://archive.org/details/stackexchange) (per-table XML only). As on the PostgreSQL side every site shares one schema, so they all build through a single shared hook (`mysql/scripts/stackexchange`; each site's `mysql/scripts/<site>` directory is a symlink to it). The hook is the MySQL-emitting counterpart of the PostgreSQL one: it converts the XML to `CREATE TABLE` + batched `INSERT`s + indexes, mapping PostgreSQL `int`/`timestamp`/`text` to `INT`/`DATETIME(6)`/`MEDIUMTEXT` and adding a key-prefix length to indexes on text columns (MySQL cannot index a full `TEXT`). Counts match the PostgreSQL sites exactly and, since the upstream dumps are refreshed periodically, are recorded as floors. The sites currently shipped (database name in parentheses): `stackexchange-beer` (`beer`), `stackexchange-coffee` (`coffee`), `stackexchange-poker` (`poker`), `stackexchange-woodworking` (`woodworking`), `stackexchange-chess` (`chess`), and `stackexchange-cooking` (`cooking`, the largest — ~500k votes, ~230k post-history rows).

The next group of datasets has no MySQL-native source, but their PostgreSQL dumps are essentially DDL + data, so we hand-translate the dialect at build time through a shared `mysql/scripts/pgsql` transform hook (each dataset's `mysql/scripts/<dataset>` directory is a symlink to it). The hook converts `COPY` blocks to batched `INSERT`s, rewrites PostgreSQL types to their MySQL equivalents (`character varying`→`varchar`, `timestamp`→`datetime`, `double precision`→`double`, bare `numeric`→`decimal`, and `text`→`varchar(255)` so a text column can serve as a key, which MySQL forbids for `TEXT`), drops PostgreSQL-only noise (sequences, `OWNER TO`, `GRANT`/`REVOKE`, `USING btree`/`hash`/`lsm`, schema qualifiers), lower-cases table identifiers, transcodes Latin-1 dumps to UTF-8, and drops any PL/pgSQL stored functions (which have no mechanical MySQL translation — the schema and all data still load). Row counts match the PostgreSQL datasets exactly.

* `iso3166`: ISO 3166 country and subdivision codes — `country` and `subcountry` (2 tables in the `iso3166` database). Sourced from the [pgFoundry dbsamples](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) PostgreSQL tarball; the only MySQL-specific touch beyond the shared hook is that `two_letter` (the country primary key, referenced by `subcountry`) becomes `varchar` so it can be a key.
* `frenchtowns`: French regions, departments, and communes — `regions`, `departments`, and `towns` (3 tables in the `frenchtowns` database; ~36k towns). Sourced from the pgFoundry `french-towns-communes-francaises` tarball. The dump declares CamelCase tables (`Regions`) but loads lower-case (`regions`), which the hook reconciles by lower-casing table names; accented commune names survive the conversion (the source is UTF-8).
* `usda`: the USDA National Nutrient Database (release SR18) — food descriptions, nutrient data, weights, and references (10 tables in the `usda` database; ~254k nutrient rows). Sourced from the pgFoundry `usda` tarball, which is Latin-1 encoded — the hook transcodes it to UTF-8 before loading.
* `pgexercises`: the "clubdata" database behind [pgexercises.com](https://pgexercises.com/) — a country club's members, bookable facilities, and bookings (3 tables in the `pgexercises` database). Sourced from [Yugabyte's sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample) (the same dump behind the PostgreSQL `yugabyte-pgexercises` tag). Upstream it lives in a dedicated `cd` schema; since each MySQL image is a single database, the hook strips the `cd.` qualifier so it loads into the `pgexercises` database.
* `sportsdb`: the SportsDB sports statistics model — a generic schema covering events, persons, teams, seasons, plus American football, baseball, basketball, and ice hockey stats (107 tables in the `sportsdb` database; motor racing, soccer, tennis, wagering, and weather tables are schema-only, matching the PostgreSQL side). Sourced from [Yugabyte's sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample) (the same dump behind the PostgreSQL `sportsdb`/`yugabyte-sportsdb` tags), which ships as five PostgreSQL files (tables, INSERT data, indexes, constraints, FKs). Beyond the shared hook's usual fixes it drops Yugabyte's `USING lsm` index access method and an unused `CREATE DOMAIN`; the 96 unique constraints and 137 foreign keys survive the translation.
* `dellstore`: the Dell DVD Store ("dellstore2") sample — a small e-commerce model of customers, orders, order lines, products, and inventory (8 tables in the `dellstore` database; ~20k customers, ~12k orders). Sourced from the [pgFoundry dbsamples](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) PostgreSQL tarball. The dump ships a `new_customer` PL/pgSQL stored function (an application helper, not used by the schema); since stored procedures have no mechanical PostgreSQL→MySQL translation, the hook drops it — the schema, primary keys, foreign keys, and all data still load.

### MySQL tags

Available MySQL tags are `sakila`, `world`, `chinook`, `northwind`, `moma`, `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `sportsdb`, `dellstore`, `stackexchange-beer`, `stackexchange-coffee`, `stackexchange-poker`, `stackexchange-woodworking`, `stackexchange-chess`, `stackexchange-cooking` and `latest`. Each image carries exactly one dataset, loaded into a database of the same name. `latest` currently tracks the `world` dataset (mirroring the PostgreSQL `latest`).

### Datasets not ported to MySQL

The remaining PostgreSQL datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features (PL/pgSQL, extensions, `pg_dump` internals) that can't be hand-translated without diverging from the upstream dataset. Plain DDL + data dumps are instead hand-translated (see the group above); these are the ones that remain PostgreSQL-only:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL, and MySQL uses the original Sakila directly (tag `sakila`, above).
* `adventureworks`: the only maintained open port ([lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres)) targets PostgreSQL. AdventureWorks is a Microsoft SQL Server sample with no comparable, maintained MySQL port, and its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to hand-translate faithfully.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish PostgreSQL `pg_dump` and leans on PostgreSQL features (`jsonb`, several million inlined rows); it is PostgreSQL-only.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) is PostgreSQL-specific — its views rely on the `tsm_system_rows` extension (no MySQL equivalent), so a port would have to drop them and would no longer be the upstream dataset.
* `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-sportsdb`: superseded on MySQL by the native/ported `chinook`, `northwind`, and `sportsdb` tags above (the Yugabyte SQL is PostgreSQL dialect; `sportsdb` is hand-translated from the same dump, so the prefixed tag is not duplicated here).

## Usage

You can start the container by running:
```
docker run -d --name pg-ds-<tag> aa8y/postgres-dataset:<tag>
```
and access it by:
```
docker exec -it pg-ds-<tag> psql -d <db_name>
```
where `<tag>` is one of the tags mentioned [here](#tags) and `<db_name>` is the database name which is one of the dataset names mentioned [here](#datasets). You can also use them with `docker-compose`. See [this example](https://github.com/aa8y/data-dude/blob/master/docker-compose.yml) for information on how to use them.

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

## Future Work

* [MySQL](https://www.mysql.com/) images are now shipped (see [MySQL images](#mysql-images)), including the full Stack Exchange family. Remaining MySQL work: port more of the PostgreSQL datasets where a MySQL-native source can be found or the upstream is format-neutral enough to hand-translate faithfully (see [Datasets not ported to MySQL](#datasets-not-ported-to-mysql)).
* Images for other popular databases.
* Find and add more free data sources.
