# Apache Pinot images — `aa8y/pinot-dataset`

The Pinot images follow the same one-dataset-per-image model as the rest of the repo, but they get there differently. [Apache Pinot](https://pinot.apache.org/) is a distributed OLAP store, not a SQL database: its unit of storage is an immutable **segment**, its DDL is not SQL at all but a pair of JSON documents per table (a *schema* and a *table config*) POSTed to a running controller, and the official image's entrypoint is `pinot-admin.sh`, a CLI multiplexer with no init-script convention. So the build cannot hand a dump to a client the way the PostgreSQL and CockroachDB images do, and there is no single-file database to bake the way SQLite and DuckDB do.

Instead the build **decompiles** each dataset — parsing the source's DDL for column names and types and its data for rows — into per-table CSV plus that pair of JSON documents plus a manifest of exact row counts, and a wrapper entrypoint starts a one-container cluster at container start and replays them over Pinot's REST API. It is still the server engines' init-at-start model; the mechanism is HTTP rather than SQL. See the [Dockerfile](Dockerfile) and [`manifest.yml`](../manifest.yml) for the wiring, and [`entrypoint`](entrypoint) for the start-up sequence.

The available tags are the Pinot column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[Apache Pinot](https://pinot.apache.org/) as [`aa8y/pinot-dataset`](https://hub.docker.com/r/aa8y/pinot-dataset), built on the official [`apachepinot/pinot`](https://hub.docker.com/r/apachepinot/pinot) image (multi-arch `amd64` + `arm64`, Java 21 on Ubuntu 24.04, pinned in the [Dockerfile](Dockerfile)). It is by far the heaviest base in this repo — roughly 2.6 GB on disk, because Pinot is a JVM application assembled from some forty plugin jars and upstream publishes no slim variant — but every tag here shares those layers, so the cost is paid once per host rather than once per dataset.

Two things are changed on top of it:

* **`JAVA_OPTS`** drops from the base image's `-Xms4G -Xmx4G` to `-Xms512M -Xmx2G`. That is a production-cluster figure on a container running one node holding one sample dataset; OFFLINE segments are memory-mapped rather than heaped, so the heap only has to cover query execution and the largest single segment build. Measured peak container memory across the shipped tags is **1.04 GB (`iso3166`) to 1.30 GB (`moma`)** — the whole range sits inside the 2 GB ceiling with room to spare.
* **The entrypoint** is a wrapper that starts the cluster and loads the dataset. It still forwards any arguments to `pinot-admin.sh`, so the base image's own interface (`docker run <image> QuickStart -help`) keeps working; only a bare `docker run` starts a dataset cluster.

## Topology

Everything runs in one container, in two JVMs:

* **ZooKeeper** on 2181, in its own small JVM (`-Xmx256M`). Pinot's cluster state lives in Apache Helix, which needs ZooKeeper, and `StartServiceManager -bootstrapServices` only knows the `CONTROLLER`/`BROKER`/`SERVER`/`MINION` roles — `ZOOKEEPER` is not a Pinot service role, so it cannot be bootstrapped alongside them.
* **Controller (9000), broker (8099) and server (8098 query / 8097 admin)** in a second JVM, via `StartServiceManager` and the three [`conf/`](conf) files. `QuickStart -type EMPTY` would also give a one-JVM cluster, but it assigns its own ports (broker 8000, server 7050, ZooKeeper 2123) and starts a minion nobody here needs, so the container would not answer on the ports the base image exposes.

Runtime state — the controller's deep store and the server's segment directory — lives under `/var/lib/pinot`, deliberately *not* under `/opt/pinot/data`, which the base image declares as a `VOLUME`.

## Usage

```
docker run -d -p 9000:9000 -p 8099:8099 --name pinot-ds-<tag> aa8y/pinot-dataset:<tag>
```

where `<tag>` is one of the tags in the Pinot column of the [matrix](../README.md#dataset-support-matrix).

**First start takes roughly 30–40 seconds** on an unloaded host — 27 s for the smallest dataset, 40 s for `moma` — and materially longer on a busy or memory-constrained one, because two JVM starts and Helix settling account for a fixed ~25 s of it and the rest is turning the shipped CSVs into real Pinot segments. The container prints one unmistakable line when it is genuinely ready:

```
pinot-dataset: world ready (3 tables)
```

That marker is printed only after every table has been created, ingested, *and* polled until `SELECT COUNT(*)` returns the exact row count recorded at build time — so there is no window in which a half-loaded dataset looks up. (`docker logs -f pinot-ds-<tag>` to watch for it; Pinot is chatty on the way there.)

Once it appears, the **query console and cluster manager** are at <http://localhost:9000>, and the broker takes SQL over HTTP:

```
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT continent, COUNT(*) FROM country GROUP BY continent ORDER BY 2 DESC"}' \
  http://localhost:8099/query/sql
```

To see NULLs as NULLs rather than as each column's default value, prefix the statement with Pinot's null-handling query option (see [Nulls and defaults](#nulls-and-defaults) below):

```
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"sql":"SET enableNullHandling=true; SELECT code, gnp, gnpold FROM country LIMIT 5"}' \
  http://localhost:8099/query/sql
```

The controller's REST API is on the same port as the console — `curl -s http://localhost:9000/tables` lists what the image carries.

## How a dataset becomes a Pinot table

One **source table becomes one Pinot table with the same name**. Pinot has no databases and no schemas — a cluster is a flat namespace of tables — and each image carries exactly one dataset, so nothing is qualified: `world`'s `city` is just `city`. Every table is an **OFFLINE** table with `replication: 1`.

**No time column.** OFFLINE tables do not require one, and none of these datasets has a natural candidate, so `segmentsConfig` has no `timeColumnName` rather than a synthesized constant column the source never had. Practically this means no time-range pruning and no retention — neither of which a fixed sample dataset wants.

**Every column is a dimension.** Pinot's other two field categories would each cost fidelity here: a metric field defaults a null to `0`, and a date-time field would force the time column just ruled out.

**Type mapping**, from the source DDL, verified against Pinot 1.5.0:

| PostgreSQL | Pinot | note |
| --- | --- | --- |
| `smallint`, `integer`, `serial` | `INT` | |
| `bigint`, `bigserial` | `LONG` | |
| `real` | `FLOAT` | |
| `double precision`, `numeric`, `decimal`, `money` | `DOUBLE` | not `BIG_DECIMAL`: it ingests cleanly but cannot be dictionary-encoded and several aggregations return it as a string. The affected columns are money-ish and all fit a double exactly at their scale. |
| `boolean` | `BOOLEAN` | values are normalized to `true`/`false` at build time. PostgreSQL's `COPY` writes `t`/`f`, and Pinot's BOOLEAN parser reads *both* of those as `false`, silently. |
| `date`, `timestamp` | `TIMESTAMP` | stored as millis since the epoch, in UTC. |
| everything else | `STRING` | `character(n)`, `varchar`, `text`, `bytea`, … |

**What is dropped.** Everything Pinot has nowhere to put: primary and foreign keys, `CHECK` constraints, `UNIQUE`, sequences, `GRANT`, schemas, and dellstore's PL/pgSQL function. Pinot enforces no constraints at all, and its indexes are declared in the table config rather than in DDL. This is a much larger loss of fidelity than the other engines' — worth knowing before you use these images to test constraint behaviour, and irrelevant if you are here to practise analytical SQL.

### Nulls and defaults

Pinot's default behaviour is to replace a null with its column's **default value** — `"null"` for a STRING, `Integer.MIN_VALUE` for an INT, `-Infinity` for a DOUBLE. These tables set `nullHandlingEnabled`, which stores a real null vector, so with `SET enableNullHandling=true;` a NULL comes back as a JSON `null`. **Without that query option you get the default value instead**, which is a genuine footgun on `SELECT *` and on aggregates.

One fidelity loss remains and is not fixable from this side: **Pinot reads an empty CSV field as null**, so a column that held an empty string upstream is indistinguishable from one that held NULL. The build writes SQL NULL as an explicit `\N` sentinel (and tells Pinot to read it as null) precisely so the sentinel itself is never mistaken for data, but the reverse conflation stands.

## Pinot datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are Pinot-specific:

* `world`, `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`: the same PostgreSQL dumps the SQLite and DuckDB tags use, run through the shared [`scripts/pgsql`](scripts/pgsql/transform) transform hook, which parses the `CREATE TABLE` DDL and both data spellings these dumps use — `COPY ... FROM stdin` blocks and (for pgexercises) multi-row `INSERT`s. **Row counts match the PostgreSQL and DuckDB tags exactly.** Table and column names are folded to lower case, following PostgreSQL's own rule for unquoted identifiers — which matters for `frenchtowns`, whose dump declares `Regions` but loads `COPY regions`, and which is why these table names differ from the DuckDB tag's case-preserved ones. `pgexercises`' `cd` schema qualifier is dropped (Pinot has no schemas), and `dellstore`'s empty `reorder` table still ships as a header-only CSV so it becomes a real 0-row segment and answers `count(*) = 0` rather than nothing at all.
* `geonames`: the GeoNames `cities15000` export — one `cities` table, 19 columns in the order the export's `readme.txt` documents. The schema is authored in-repo ([`scripts/geonames/schema.sql`](scripts/geonames/schema.sql)) in plain PostgreSQL DDL and parsed with the *same* `CREATE TABLE` reader the pgsql hook uses, so an authored schema and a real dump go through one type map. The export is tab-separated with no quoting at all, so it is split on tabs rather than parsed as CSV — a double quote in a place name is a literal character. Counts drift as GeoNames rebuilds the dump daily, so the smoke test records floors.
* `openflights`: airports, airlines and routes, schema authored in-repo ([`scripts/openflights/schema.sql`](scripts/openflights/schema.sql), 3 tables). The published files are already RFC4180 CSV and mark a missing value with an unquoted `\N` — which is exactly the NULL sentinel used here, so those fields pass straight through. No foreign keys (`routes` deliberately keeps dangling airport/airline references). Counts drift upstream, recorded as floors.
* `moma`: the MoMA research collection — ~177k rows across `artists` and `artworks`, and the bulkiest tag here by some distance (82 MB of shipped CSV against usda's 19 MB, because `artworks` is 30 columns of free text; usda has more rows, 368k, in far less space). Schema authored in-repo ([`scripts/moma/schema.sql`](scripts/moma/schema.sql)), **every column `STRING`** — the same choice the CockroachDB tag makes, and a sharper one here: the exports carry approximate dates like `c. 1950` and blank measurements, and on Pinot a value a column's type cannot parse is not an error, it is silently replaced by that type's default. Rows are padded or truncated to the declared width so a refreshed export with an extra trailing column still loads. Counts drift as MoMA refreshes its exports, recorded as floors.

## Datasets not ported to Pinot

Pinot is an analytical store for flat, denormalized tables, which makes the rest of the repo's catalogue a poor fit for reasons that are mostly about the engine rather than the data:

* `chinook`, `northwind`, `sakila`/`pagila`, `sportsdb`, `adventureworks`: highly normalized OLTP schemas whose whole point is the joins between fifteen to a hundred small tables. Pinot's default (v1) query engine cannot join at all, and its multi-stage engine is off by default, so these would load as a pile of tables nobody could usefully query together. Loading them anyway would misrepresent both the dataset and the engine.
* `stackexchange-<site>`: the per-table XML dumps convert cleanly enough, but the interesting queries are all self-joins (`Posts` to `Users` to `Comments`) — the same objection as above — and each site would add a multi-gigabyte tag on an already 2.6 GB base.
* `airlines`: the [postgrespro demo](https://postgrespro.com/education/demodb) is distributed as a binary-ish `pg_dump` and leans on `jsonb`, which has no Pinot column type.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) relies on the `tsm_system_rows` extension and ships views, neither of which Pinot has.
* `employees`: MySQL-native, and the port would inherit the join objection above.
* `nyc-taxi`: the best fit of all of these — a single wide 4.3M-row fact table with a real time column, which is the exact shape Pinot exists for. It is not shipped yet because it needs a different load path (Pinot's Parquet record reader via `LaunchDataIngestionJob`, rather than the controller's synchronous CSV endpoint the other tags use) and a heap large enough to build a segment that size. It is the obvious next tag.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c pinot -t world
```

To add or change a Pinot dataset, declare its `extractUrl`, `sqlFiles` (for a SQL-sourced dataset) and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args — and add a `scripts/<dataset>/transform` hook if the dataset is not one the shared `scripts/pgsql` hook can read. See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
