# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

Have you ever wanted to access pre-populated databases with dummy but valid data? It can be for something as simple as practicing writing SQL queries to running tests on databases. Under such circumstances, you have to either have to create dummy data or utilize some internet-searching skills to find data to populate your database. I think this is a common enough problem/requirement that solution can be Dockerized for reuse. So here is a Docker image for [PostgreSQL](https://www.postgresql.org/) with databases populated with sample data.

## Datasets

So far we have the following datasets which are being used in the images.
* [Postgres Sample Databases](https://wiki.postgresql.org/wiki/Sample_Databases): The datasets being used from here are `dellstore2` (tagged `dellstore`), `french-towns-communes-francaises` (tagged `frenchtowns`), `iso3166`, `usda` and `world`, all sourced from PostgreSQL's FTP mirror of [pgFoundry dbsamples](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/).
* `sportsdb`: the original `www.sportsdb.org` download is no longer available, so we use the mirror Yugabyte ships in [its sample data repo](https://github.com/yugabyte/yugabyte-db/tree/master/sample). This mirror defines all 107 sportsdb tables but only populates data for the generic infrastructure tables (events, persons, teams, seasons, etc.) plus american football, baseball, basketball, and ice hockey stats. Motor racing, soccer, tennis, wagering, and weather tables are schema-only.
* `omdb`: the [Open Media Database](https://www.omdb.org/) film catalogue, packaged for Postgres at [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql). CSV data is fetched from `www.omdb.org` at build time and shipped inside the image so `\copy` resolves at container start. The init script also creates the `tsm_system_rows` extension that the upstream views rely on. Heads up: this dataset is much larger than the others (~150 MB of CSV + indexes), which makes the `omdb` and `all`/`latest` images noticeably heavier.
* `adventureworks`: the Microsoft AdventureWorks 2014 OLTP sample (a fictitious bicycle parts wholesaler — 68 tables, 5 schemas, ~300 employees, 500 products, 20k customers, 31k sales). We use the [lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres) port, which pulls Microsoft's CSV bundle and runs a Ruby reformat before loading. CSVs ship alongside the init script so the upstream `\copy ./X.csv` directives resolve at container start. This dataset is also on the heavier side (~90 MB of CSV).

## Databases

The only database supported so far is [PostgreSQL](https://www.postgresql.org/). We use the `alpine` version of the official image as the base image to keep our image slim.

## Tags

Available tags are `adventureworks`, `dellstore`, `frenchtowns`, `iso3166`, `omdb`, `sportsdb`, `yugabyte-sportsdb`, `usda`, `world`, `all` and `latest`. `all` and `latest` are the same image with all the datasets in one image. Each of them has been loaded into their own database in the image. The rest of the tags belong to images single datasets. All tags are published for `linux/amd64` and `linux/arm64`.

`sportsdb` and `yugabyte-sportsdb` are currently the same image — the only mirror we ship is Yugabyte's. The mirror-explicit `yugabyte-sportsdb` tag exists so that if we add another sportsdb mirror later (e.g. a hypothetical `pgfoundry-sportsdb`), users can pin to the specific source they want while `sportsdb` continues to track whichever mirror is the current default.

### `pagila` has been removed

The `pagila` tag has been removed due to the fact that it was broken for a while and it also broke the `all` and `latest` tags. This is because the Pagila dataset we were using had a change which was not compatible with any version of Postgres (See [#1](https://github.com/aa8y/docker-dataset/issues/1) and [this issue](https://github.com/devrimgunduz/pagila/issues/6) for context.

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

If you want to build a custom image with not one or all the datasets, but some, then you can do that using:
```
docker build -t aa8y/postgres-dataset:some --build-arg DATASETS=dellstore,world .
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
These are wired into `dave test` via the `test:` template in `manifest.yml`,
which renders per tag and passes the image tag plus the comma-separated list
of datasets baked into it (so multi-dataset tags like `all` are checked across
every database). The script needs `docker` and `jq` on the host; `psql` runs
inside the container.

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
