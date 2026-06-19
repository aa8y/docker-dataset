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
* `adventureworks`: the Microsoft AdventureWorks 2014 OLTP sample (a fictitious bicycle parts wholesaler — 68 tables, 5 schemas, ~300 employees, 500 products, 20k customers, 31k sales). We use the [lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres) port, which pulls Microsoft's CSV bundle and runs a Ruby reformat before loading. CSVs ship alongside the init script so the upstream `\copy ./X.csv` directives resolve at container start. This dataset is also on the heavier side (~90 MB of CSV).
* `airlines`: the [postgrespro "airlines" demo database](https://postgrespro.com/education/demodb) — a flight-booking model (airports, flights, tickets, bookings, boarding passes, seats; 9 tables in a `bookings` schema, with `search_path` defaulting to it). We ship the smallest ("3 months") English snapshot. Upstream distributes it as a single gzipped `pg_dump` that manages its own `demo` database, so the build decompresses it and strips the `DROP/CREATE DATABASE demo` / `\connect` directives (retargeting the `ALTER DATABASE` options) so it loads into the `airlines` database. Heads up: this is the largest dataset — the dump inlines several million rows (boarding passes, segments, tickets), so the image is heavy. The snapshot URL is date-stamped, so it may need bumping if postgrespro retires the pinned file.
* `moma`: the [Museum of Modern Art research collection](https://github.com/MuseumofModernArt/collection) — ~160k catalogued artworks and ~16k artists (2 tables in the `public` schema). MoMA publishes only CSV/JSON (no SQL), so the schema is authored in-repo (`postgres/scripts/moma/schema.sql`, every column `text` since the data is free-form) and the CSVs ship alongside the init script so `\copy` resolves at container start. Note: MoMA refreshes the published CSVs periodically, so exact row counts drift over time.
* `beer` (tagged `stackexchange-beer`): the [Beer Stack Exchange](https://beer.stackexchange.com/) Q&A site — posts, comments, users, votes, badges, tags, post links, and post history (8 tables in the `public` schema). Sourced from the [Stack Exchange data dump on archive.org](https://archive.org/details/stackexchange), which ships only per-table XML. Adapting the schema, column mapping, and indexes from [stackexchange-dump-to-postgres](https://github.com/Human-Centric-Machine-Learning/stackexchange-dump-to-postgres), a build hook (`postgres/scripts/beer/transform`) converts the XML into SQL — `CREATE TABLE` + inline `COPY` + indexes — rather than running the upstream importer against a live server, which keeps the dataset within our extract/transform/load build (no database running at build time). Unknown attributes from newer dumps are ignored, and since the upstream dump is refreshed periodically, counts are recorded as floors.

## Databases

The only database supported so far is [PostgreSQL](https://www.postgresql.org/). We use the `alpine` version of the official image as the base image to keep our image slim.

## Tags

Available tags are `adventureworks`, `airlines`, `dellstore`, `frenchtowns`, `iso3166`, `moma`, `omdb`, `pagila`, `stackexchange-beer`, `sportsdb`, `yugabyte-sportsdb`, `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-pgexercises`, `usda`, `world` and `latest`. Each image carries exactly one dataset, loaded into its own database. `latest` currently tracks the `world` dataset. All tags are published for `linux/amd64` and `linux/arm64`.

`sportsdb` and `yugabyte-sportsdb` are currently the same image — the only mirror we ship is Yugabyte's. `sportsdb` is a special case: it predates the mirror-explicit naming, so we keep the bare `sportsdb` tag working for backwards compatibility while `yugabyte-sportsdb` exists so that if we add another sportsdb mirror later (e.g. a hypothetical `pgfoundry-sportsdb`), users can pin to the specific source they want and `sportsdb` continues to track whichever mirror is the current default.

The other Yugabyte-sourced datasets — `chinook`, `northwind`, and `pgexercises` — have no legacy bare tags to preserve, so they ship under their `yugabyte-`prefixed tags only (`yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-pgexercises`). The database name inside each image is still the bare dataset name (`chinook`, `northwind`, `pgexercises`). If we ever add a second mirror for one of these, the prefixed tag already disambiguates the source.

Stack Exchange is a family of sites rather than a single dataset, so — like the `yugabyte-` tags — its tag carries the source-and-site prefix: `stackexchange-beer`. The database inside is the bare site name (`beer`). Adding another site later is just another `stackexchange-<site>` tag built by the same hook.

### `all` has been retired

The multi-dataset `all` tag (and the all-datasets `latest`) is legacy: images are now one dataset each. If you need several datasets together, run one container per dataset (e.g. via `docker-compose`), or build a custom image per dataset.

### `pagila` was removed and re-added

`pagila` was [removed in 2019](https://github.com/aa8y/docker-dataset/issues/1) because the upstream source shipped a change that wouldn't load on any Postgres version, which back then also took down the combined `all`/`latest` images. Both causes are now gone: the [upstream fork](https://github.com/devrimgunduz/pagila) loads cleanly on modern Postgres (tested against 12+), and images are now one dataset each, so a single dataset can no longer break the others. It is therefore back as a regular tag.

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

* Images for other popular databases like [MySQL](https://www.mysql.com/).
* Find and add more free data sources.
