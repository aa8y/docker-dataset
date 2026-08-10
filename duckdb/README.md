# DuckDB images — `aa8y/duckdb-dataset`

The DuckDB images follow the same one-dataset-per-image model, and — like SQLite — DuckDB is embedded, so the build inverts the server engines' pattern: rather than shipping init scripts that run at container start, the build assembles the database file and the final image carries it. Each [`aa8y/duckdb-dataset`](https://hub.docker.com/r/aa8y/duckdb-dataset) image carries exactly one dataset as `/data/<dataset>.duckdb`, built through the [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml): a dataset is described either by a text SQL source (fed to the `duckdb` CLI to build the database) or by a prebuilt DuckDB database file (shipped as-is).

The available tags are the DuckDB column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[DuckDB](https://duckdb.org/) as [`aa8y/duckdb-dataset`](https://hub.docker.com/r/aa8y/duckdb-dataset), built on the official [`duckdb/duckdb`](https://hub.docker.com/r/duckdb/duckdb) image (multi-arch, pinned in the [Dockerfile](Dockerfile)). That image is distroless — a glibc-linked `/duckdb` binary and nothing else, no shell — which shapes the build (a glibc loader stage assembles the database file, since neither the Alpine builder nor the shell-less final image can) and the image's fixed `CMD`: with no shell to expand variables, every image opens the same `/data/db.duckdb` symlink, which points at that image's dataset file.

## Usage

Start a container and open the database with the bundled `duckdb` shell:
```
docker run -it --rm aa8y/duckdb-dataset:<tag>
```
which opens `/data/db.duckdb` (a symlink to `/data/<db_name>.duckdb`) directly. You can also run a one-off query — the image has no shell, so the arguments replace the `CMD` and must name the binary by its absolute path:
```
docker run --rm aa8y/duckdb-dataset:<tag> /duckdb -readonly -csv -c "SELECT count(*) FROM ..." /data/<db_name>.duckdb
```
where `<tag>` is one of the tags in the DuckDB column of the [matrix](../README.md#dataset-support-matrix) and `<db_name>` is the matching dataset name.

## DuckDB datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are DuckDB-specific:

* `chinook`: built at image-build time from the same pinned vendor script as the SQLite tag (`Chinook_Sqlite.sql`, release `v1.4.5`), rewritten for DuckDB by the [`scripts/chinook`](scripts/chinook/transform) transform hook — DuckDB's PostgreSQL-derived parser rejects the script's bracket-quoted identifiers, and it validates `FOREIGN KEY` references at `CREATE` time where SQLite tolerates the script's forward references, so brackets become double quotes (leaving data like `'BBC Sessions [Disc 1]'` untouched) and the FK constraints are dropped (mirroring what the shared pgsql hooks do for other engines). CamelCase identifiers (`Track`, `InvoiceLine`), with row counts matching the other `chinook` tags exactly.
* `world`, `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`: the same PostgreSQL dumps the SQLite tags use, run through the shared [`scripts/pgsql`](scripts/pgsql/transform) transform hook. Because DuckDB's parser *is* PostgreSQL-derived, that hook is a thin one next to SQLite's: it converts `COPY ... FROM stdin` blocks to batched `INSERT`s (DuckDB's `COPY` reads files, not inline data), transcodes the Latin-1 dumps, and removes only what DuckDB genuinely cannot run — `SET`, `setval`, `GRANT`, `USING btree`, `serial`, `FOREIGN KEY`s, PL/pgSQL. PostgreSQL casts, column types, `CHECK` constraints and `ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY` all survive, so these tags keep their primary keys where the SQLite ones cannot. Row counts match the SQLite tags exactly. One cosmetic difference: `frenchtowns` keeps the dump's declared `Regions` / `Departments` / `Towns` spelling, since DuckDB is case-preserving — and case-insensitive, so `select * from regions` resolves anyway.
* `moma`: the MoMA research collection, published only as CSV, so the schema is authored in-repo ([`scripts/moma`](scripts/moma/schema.sql)) and the CSVs are bulk-loaded with `COPY <table> FROM '<file>.csv' (FORMAT CSV, HEADER)` — DuckDB reads CSV in plain SQL, so unlike the SQLite tag no dot-commands are involved. Same two tables (`artists`, `artworks`) and column order as the other engines. Counts drift as MoMA refreshes its exports, so the smoke test records floors.
* `nyc-taxi`: the NYC TLC yellow-taxi trip records — 4,322,960 rows in one `trips` table, and the only dataset here that ships as **Parquet**, the format DuckDB exists to read. The [`scripts/nyc-taxi`](scripts/nyc-taxi/transform) hook authors a single `CREATE TABLE trips AS FROM read_parquet(...)` (Parquet support is compiled into the CLI, so no extension is loaded), and the Parquet file itself stays behind in the build — only the database ships. The month is **pinned** (`yellow_tripdata_2025-06.parquet`) because TLC publishes monthly and revises older months in place, so an unpinned URL would make the row count drift. Column names and types are the TLC's own.
* `stackexchange-<site>` (`beer`, `chess`, `coffee`, `cooking`, `poker`, `woodworking`): converted from each site's per-table XML dump by [`scripts/stackexchange`](scripts/stackexchange/transform), as on the other engines. The DuckDB emitter differs from the SQLite one in two places: no SQLite `PRAGMA` preamble (DuckDB rejects those settings), and `CreationDate` and friends are real `TIMESTAMP` columns rather than ISO 8601 text — matching the PostgreSQL/MySQL/CockroachDB tags, so date comparisons compare dates. Counts drift as archive.org refreshes the dumps, so the smoke test records floors.

Not yet ported: `northwind`, `sakila` (both ship as prebuilt SQLite database files, which DuckDB cannot open directly) and `sportsdb`.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c duckdb -t chinook
```

To add or change a DuckDB dataset, declare its `extractUrl`, `sqlFiles` (or `dbFile` for a prebuilt database) and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
