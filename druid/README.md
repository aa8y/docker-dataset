# Apache Druid images — `aa8y/druid-dataset`

The Apache Druid images follow the same one-dataset-per-image model as the rest of the repo, but Druid changes what "loading a dataset" means. It is a real-time OLAP datastore built around immutable **segments**: there is no `CREATE TABLE` + `INSERT`/`COPY` path at all, and data exists only once an **ingestion task** has written segments for it. So these images ship, per table, a CSV data file plus a native batch ingestion spec, and the container's entrypoint submits every spec on first boot and waits for the segments to be published, loaded and queryable before it announces readiness. One table becomes one **datasource** of the same name, so `SELECT * FROM city` reads the same here as on the relational engines.

Each [`aa8y/druid-dataset`](https://hub.docker.com/r/aa8y/druid-dataset) image is built through the [Dockerfile](Dockerfile) driven by [`manifest.yml`](../manifest.yml). The available tags are the Druid column of the [dataset support matrix](../README.md#dataset-support-matrix), which also lists each dataset's upstream source.

## Base image

[Apache Druid](https://druid.apache.org/) 37.0.0 on [`eclipse-temurin:21-jre-alpine`](https://hub.docker.com/_/eclipse-temurin), built from the **binary distribution** rather than `FROM apache/druid`.

That is not a preference, it is a constraint. Every published `apache/druid` tag is **amd64-only** — the upstream image builds Druid's web console during its own build, which does not resolve on arm64, so its Dockerfile pins `--platform=linux/amd64` — while this repo publishes every image for `linux/amd64` *and* `linux/arm64` on native runners. Druid itself is pure Java and architecture-independent, so the build fetches the pinned release tarball, verifies it against the SHA-512 published at [downloads.apache.org](https://downloads.apache.org/druid/37.0.0/) (pinned in the Dockerfile, so the bytes are the ones this repo was written against), trims it, and lays it on the multi-arch Temurin JRE.

Java 21 rather than 17 for the same reason: Druid 37 supports both, but `eclipse-temurin:17-jre-alpine` is published for amd64 only. Alpine rather than a glibc variant purely for size — Druid is pure Java, and the one place musl would show up, the distribution's own `bash` launcher scripts, is covered by installing `bash`.

The distribution is trimmed from 687 MB to 279 MB. `extensions/` is 474 MB of it and Druid loads only what `druid.extensions.loadList` names, so all but one are dropped: nothing these images do reaches HDFS, S3, Azure, GCS, Kafka, Kinesis, Kubernetes, Avro, ORC, Protobuf or the security extensions. `quickstart/` (the tutorial's own sample data and specs) goes too. `LICENSE`, `NOTICE` and `licenses/` stay — they are the Apache-2.0 attribution that has to travel with a redistributed binary release. The one kept, `druid-parquet-extensions` (68 MB), is not loaded by any dataset shipped today; it is there because Parquet is the obvious next source format for this engine and adding it later would otherwise change the base image for every tag. `--build-arg DRUID_EXTENSIONS=` drops it, and a space-separated list keeps others; the entrypoint refuses to start if a dataset asks for one the image does not have, so a trimmed extension can never be half-referenced.

Services are started the way the official image starts them — `bin/run-java` (which supplies the `--add-exports`/`--add-opens` flags Java 17+ needs) against the distribution's own `conf/druid/single-server/nano-quickstart` profile, with `DRUID_SINGLE_NODE_CONF` and the `druid_*` environment convention both honoured — so what you know about `apache/druid` still applies. The one deliberate difference: where the official `druid.sh` rewrites `runtime.properties` files before launching, [`druid-dataset.sh`](druid-dataset.sh) passes the same settings as `-D` system properties, which Druid reads at higher precedence.

## Usage

Start a container and query through the router, which is the single endpoint for SQL, the JSON APIs and the web console:

```
docker run -d -p 8888:8888 --name druid-ds-<tag> aa8y/druid-dataset:<tag>
```

Then open the **web console** at <http://localhost:8888>, or query over HTTP:

```
curl -s http://localhost:8888/druid/v2/sql \
  -H 'Content-Type: application/json' \
  -d '{"query": "SELECT continent, count(*) AS n FROM country GROUP BY 1 ORDER BY 2 DESC"}'
```

where `<tag>` is one of the tags in the Druid column of the [matrix](../README.md#dataset-support-matrix). There is no database to name: an image carries one dataset, and its tables are the datasources in the single `druid` schema — `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'druid'` lists them. The image ships `curl`, so the same query works from inside with `docker exec`.

### First start

Unlike the other server images, these do real work on first boot: six JVMs come up (ZooKeeper, coordinator-overlord, historical, middleManager, broker, router), then one indexing task runs per table, each forking a peon JVM that writes a segment, publishes it and waits for the historical to load it. **Expect 30–60 seconds** before the data is queryable — about 30 s for a small dataset like `world` and about a minute for the widest one (`usda`, ten tables). Querying before then returns an empty or partial result rather than an error, so wait for the marker:

```
docker logs druid-ds-world 2>&1 | grep 'ready ('
druid-dataset: world ready (3 datasources)
```

That line is printed only after every ingestion task has succeeded, every segment reports 100% loaded, and every datasource answers a SQL query — it is what the [smoke test](../test/integration/run-druid.sh) waits for. If any service dies, or an ingestion task fails, the entrypoint prints the tail of the relevant log and the container exits non-zero rather than sitting there half-loaded.

`docker stop` sends SIGTERM, which the entrypoint forwards to every JVM — but six of them do not all finish inside Docker's 10-second default grace period, so a plain `docker stop` ends in a SIGKILL and exit code 137. Nothing is lost when it does (`var/` lives in the container and the data is re-ingested on the next start); `docker stop -t 60` gives a clean 143 if you want one.

The cluster settles at about **1.8 GiB** of container memory, peaking near **2.2 GiB** while ingesting. That is below the stock `nano-quickstart` profile's own appetite (~1.9 GiB of heap plus ~1.2 GiB of direct memory once the peon is counted): the entrypoint shrinks every JVM and pins `druid.processing.*`, both documented at the top of [`druid-dataset.sh`](druid-dataset.sh). Raise any of it with the `druid_*` environment convention, e.g. `-e druid_processing_buffer_sizeBytes=50MiB` or `-e 'druid_indexer_runner_javaOptsArray=["-Xmx1g"]'`.

Each service also writes its own rolling log under `/opt/druid/var/log/`, which is where to look when something is wrong:

```
docker exec druid-ds-world tail -f var/log/broker.log
```

## Druid datasets

Sources are in the [matrix](../README.md#dataset-support-matrix); the notes below are Druid-specific. Every image models a table the same way — one datasource, every source column kept as a typed dimension (`long` / `double` / `string`), **rollup off** and one segment per datasource — so `count(*)` counts raw rows and matches the PostgreSQL and DuckDB tags exactly.

* `world`, `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`: the same PostgreSQL dumps the SQLite and DuckDB tags use. None of their SQL survives — Druid runs none of it — so the shared [`scripts/pgsql`](scripts/pgsql/transform) hook *reads* the dumps rather than rewriting them: it parses the `CREATE TABLE` DDL for column names, types and `NOT NULL` flags, decodes both data formats these dumps use (`COPY ... FROM stdin` and multi-row `INSERT`), and writes one CSV plus one ingestion spec per table. PostgreSQL identifier folding is honoured, so `frenchtowns` lands in `regions`/`departments`/`towns` like the PostgreSQL, MySQL, SQLite and CockroachDB tags (the DuckDB tag keeps the dump's declared case instead). Row counts match the DuckDB tags exactly, with one documented exception: **`dellstore` has seven datasources where the other engines have eight**, because its `reorder` table ships with zero rows upstream and Druid has no empty datasource — an ingestion task that produces no segments succeeds and leaves nothing behind to query, so the hook skips a zero-row table and says so at build time.
* `geonames`: the cities15000 export, whose schema is authored in-repo ([`scripts/geonames/schema.sql`](scripts/geonames/schema.sql), the same one the CockroachDB tag uses). It is the cheapest of the CSV-only datasets to handle here, because the published export *is already* COPY TEXT — tab-separated, unquoted, unescaped — so its hook staples the file onto the authored DDL and hands the result to the shared pgsql hook, re-encoding nothing. It is also the one dataset here whose `__time` is real data (see below). Counts drift as GeoNames rebuilds the dump daily, so the smoke test records floors.
* `openflights`: airports, airlines and routes, schema authored in-repo ([`scripts/openflights/schema.sql`](scripts/openflights/schema.sql), 3 tables). The published files are RFC 4180 CSV, so the hook re-emits them as COPY blocks under the authored DDL. No foreign keys — Druid has none to declare — which suits a dataset whose `routes` deliberately keeps dangling airport/airline references. Counts drift as upstream refreshes the files, so the smoke test records floors.
* `moma`: the MoMA research collection, schema authored in-repo ([`scripts/moma/schema.sql`](scripts/moma/schema.sql), every column a string, same two tables and column order as the other engines). The exports are the messiest data in this repo — ragged rows, embedded newlines and quotes — and one of those is genuinely lossy here: **Druid's CSV reader splits input into lines before parsing them**, so a value containing a newline cannot round-trip and is flattened to a single space. About 11,000 of ~176,000 values are affected, all in the free-text `artworks` columns; the build reports the count. Row counts are unaffected, and drift with MoMA's refreshes, so the smoke test records floors.

### `__time`

Druid requires every row to have a primary timestamp, and these are relational tables that mostly have no natural one. The hook picks the table's first `NOT NULL` date/timestamp column when there is one and **verifies at build time that every value parses**, keeping it as an ordinary dimension too so no column is lost. Tables without one — most of them — get a constant `2000-01-01T00:00:00Z` through `timestampSpec.missingValue`.

The build-time check is the point rather than a nicety: Druid *silently drops* a row whose timestamp will not parse, so a nullable or free-form date column would quietly change `count(*)` — exactly what these images are asserted on. Today it promotes `orders.orderdate` and `orderlines.orderdate` (dellstore), `members.joindate` and `bookings.starttime` (pgexercises), and `cities.modification_date` (geonames). Everything else is the constant.

The specs also set `queryGranularity: NONE`, not `ALL`. With rollup off, query granularity only truncates `__time`, and the `ALL` bucket begins at Druid's minimum representable instant — so `ALL` would rewrite every row's timestamp to `-146136543-09-08`, throwing away both the real timestamps above and the readable constant, in exchange for nothing.

## Datasets not ported to Druid

Druid is an analytics store for large, flat, append-only tables, which is a poor fit for several of this repo's datasets, and the remaining gaps are mostly upstream-format problems rather than Druid ones:

* `chinook`, `sakila`/`pagila`, `northwind`, `sportsdb`: highly normalized OLTP schemas whose interest is entirely in their joins and constraints. Druid has neither foreign keys nor primary keys, and joins only in restricted forms, so the images would carry the tables while losing the thing they exist to demonstrate. `chinook` and `northwind` also ship as a prebuilt SQLite database or a quoted-CamelCase PostgreSQL dump, neither of which the shared hook reads today.
* `stackexchange-<site>`: each site ships as per-table XML, which every other engine converts with its own `scripts/stackexchange` hook. Portable here in principle — the conversion would end in the same CSV + spec — but the dumps' `Posts.Body` is HTML full of newlines, which runs straight into the CSV-reader limitation above, so a faithful port wants a JSON-lines input format rather than CSV. Deferred rather than declined.
* `nyc-taxi`: the one dataset that *should* suit Druid — 4.3 M rows, one wide fact table, a real timestamp — and the one this image's memory budget cannot afford yet. Measured rather than assumed, against the pinned TLC Parquet file: reading it is fast (~780 k rows/s), but ingesting it **runs the 256 MB peon out of heap** at its first incremental persist. Raised to a 1 GB peon it ingests all 4,322,960 rows in **110 seconds**, matching the DuckDB tag's count exactly — so the dataset works, at roughly 2.9 GiB of peak container memory and with `druid-parquet-extensions` back in the image (68 MB on *every* tag, since the extension keep-list is currently one setting for the whole context). Shipping it wants two things first: a per-tag peon heap and a per-tag extension list.
* `adventureworks`, `airlines`, `omdb`, `employees`: PostgreSQL/MySQL-specific upstreams (multiple schemas, materialized views, `jsonb`, extension dependencies, a binary `pg_dump`) with nothing Druid-shaped to map onto.

## Custom images

Each image carries one dataset, selected with the `DATASET` build arg along with that dataset's sources (declared per tag in [`manifest.yml`](../manifest.yml)). The simplest way to build a tag is through `dave`:

```
dave build -c druid -t world
```

To add or change a Druid dataset, declare its `extractUrl`, `sqlFiles` and any extras under a new tag in `manifest.yml` — the [ETL Dockerfile](Dockerfile) reads them as build args. `SQL_FILES` keeps its name for manifest uniformity across engines; here it names the ordered list of source files the transform hook reads, not files fed to a SQL client. Two more build args are specific to this engine: `DRUID_VERSION` / `DRUID_SHA512` pin the distribution, and `DRUID_EXTENSIONS` is the space-separated list of extensions to keep (empty by default). See [docs/building.md](../docs/building.md) for the full build instructions and how the build cache works.
