# SQLite images — `aa8y/sqlite-dataset`

The SQLite images follow the same one-dataset-per-image model, but since SQLite is serverless the build inverts: rather than shipping init scripts that run at container start, the build assembles the database file and the final image carries it. Each [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset) image carries exactly one dataset as `/data/<dataset>.db`, built through the [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml): a dataset is described either by a native SQLite SQL script (fed to the `sqlite3` CLI to build the database) or by a prebuilt SQLite database file (shipped as-is).

The available tags are the SQLite column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[SQLite](https://www.sqlite.org/) as [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset). SQLite is serverless — a database is just a file — so there is no server to boot and no init scripts; the build assembles the database file and the image ships it. We use the Alpine, statically-linked [`keinos/sqlite3`](https://hub.docker.com/r/keinos/sqlite3) image (multi-arch) as the base, keeping the image genuinely thin and Alpine-based.

## Usage

Start a container and open the database with the bundled `sqlite3` shell:
```
docker run -it --rm aa8y/sqlite-dataset:<tag>
```
which opens `/data/<db_name>.db` directly. You can also run a one-off query:
```
docker run --rm aa8y/sqlite-dataset:<tag> /usr/bin/sqlite3 /data/<db_name>.db "SELECT count(*) FROM ..."
```
where `<tag>` is one of the tags in the SQLite column of the [matrix](../README.md#dataset-support-matrix) and `<db_name>` is the matching dataset name.

## SQLite datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are SQLite-specific:

* `chinook`: built at image-build time from the vendor's native `Chinook_Sqlite.sql` script (release `v1.4.5`); CamelCase identifiers (`Track`, `InvoiceLine`), with row counts matching the other `chinook` tags exactly.
* `northwind`: the prebuilt jpwhite3/northwind-SQLite3 database shipped as-is — the port's *expanded* edition, whose `Orders` and especially `"Order Details"` tables carry far more rows than the classic sample, so this image is heavier than the others.
* `world`: the pgFoundry PostgreSQL `world` dump hand-translated at build time through the shared `sqlite/scripts/pgsql` transform hook (`COPY` → batched `INSERT`s, Postgres-only noise stripped); three tables (`city`, `country`, `countrylanguage`) with row counts matching the other `world` tags exactly.
* `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`, `sportsdb`: same shared `sqlite/scripts/pgsql` hook as `world` — plain PostgreSQL DDL + data dumps rewritten for SQLite at build time. SQLite cannot add constraints via `ALTER TABLE`, so PK/FK/unique constraints from the dump are dropped; tables and row counts still load faithfully (matching the MySQL tags for these datasets).
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) (same pinned `demo-20250901-3m` snapshot as the PostgreSQL tag), rewritten through the same shared `sqlite/scripts/pgsql` hook with its opt-in knobs: the dump's `bookings.` schema qualifier is stripped and its three convenience views (`airplanes`, `airports`, `timetable` — Postgres-only operators) are dropped. All nine tables load with row counts matching the PostgreSQL tag exactly; `jsonb` columns (`airplanes_data.model`, the `airports_data` names) land as plain JSON text, queryable with SQLite's built-in `json_*` functions.
* `sakila`: the bradleygrant/sakila-sqlite3 port's prebuilt `sakila_master.db` shipped as-is — stands in for PostgreSQL's `pagila` (16 base tables, MySQL-compatible row counts).
* `moma`: schema authored in-repo (`sqlite/scripts/moma/schema.sql`, every column `text`); CSVs bulk-loaded at build time with the sqlite3 CLI's `.import` dot-command. Counts drift as MoMA refreshes its exports (recorded as floors).
* `stackexchange-<site>`: per-table XML converted at build time by a shared hook (`sqlite/scripts/stackexchange`) to `CREATE TABLE` + batched `INSERT`s + indexes (double-quoted CamelCase identifiers). `cooking` is the largest; counts are recorded as floors.

## Datasets not ported to SQLite

The remaining datasets are either sourced from PostgreSQL-only upstreams or rely on PostgreSQL-specific features that can't be hand-translated without diverging from the upstream dataset. Plain DDL + data dumps are instead hand-translated (see the group above); these are the ones that remain PostgreSQL-only:

* `pagila`: not omitted but *replaced* — `pagila` is a port of Sakila to PostgreSQL, and SQLite uses a native Sakila port directly (tag `sakila`, above).
* `adventureworks`: the only maintained open port targets PostgreSQL; AdventureWorks is a Microsoft SQL Server sample with no comparable, maintained SQLite port, and its build relies on a Python reformat plus multiple schemas and materialized views — too much PostgreSQL-specific machinery to hand-translate faithfully.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) is PostgreSQL-specific — its views rely on the `tsm_system_rows` extension (no SQLite equivalent), so a port would have to drop them and would no longer be the upstream dataset.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c sqlite -t dellstore
```

To add or change a SQLite dataset, declare its `extractUrl`, `sqlFiles` and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
