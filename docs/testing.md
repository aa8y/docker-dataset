# Testing

Three layers, cheapest first — CI runs them in this order so a regression fails
as early as it can (see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

## Unit tests

Python tests for the transform hooks, under `test/unit/`, run with
`python -m pytest test/unit -q`. They need `pytest` and `lxml`
(`pip install -r test/requirements-dev.txt`) and nothing else — no Docker, no
image, no network — so the whole suite finishes in seconds and gates the image
build in CI.

The hooks are deliberately extensionless (the Dockerfiles locate them by exact
path, `scripts/<dataset>/<step>`), so `test/unit/conftest.py` imports each one
by explicit source loader and exposes it as a session fixture. Covered are the
shared, dialect-translating hooks — the ones where a subtle rewriting bug would
silently corrupt many datasets at once:

* the three PostgreSQL-dump translators: `mysql/`, `sqlite/` and
  `duckdb/scripts/pgsql/transform`,
* all five StackExchange XML emitters (postgres, mysql, sqlite, cockroach,
  duckdb),
* `cockroach/scripts/{pgfoundry,yugabyte,moma}/transform`,
* `duckdb/scripts/chinook/transform` and
  `postgres/scripts/adventureworks/transform`.

The per-dataset loader hooks that only shuttle a CSV/TSV export into a schema
authored in-repo (`geonames`, `openflights`, `employees`, `nyc-taxi`, the
non-cockroach `moma`s, `airlines`) are not unit-tested; the integration tests
below assert their loaded row counts.

## Structure tests

Static [container-structure-test][cst] configs under `test/config/` — a shared
`common.yaml` plus one file per dataset per engine. They assert on the image
filesystem and the shipped init scripts without booting a database. Which
configs apply to a tag is declared in `manifest.yml` under `structureTest:`, and
`dave structure-test` runs them natively. Alias tags (`retagFrom`) set
`structureTest: false` — no build ever produced a local image for them.

## Integration (smoke) tests

These boot each image and query the live database. There is one script per
engine, and all five source `test/integration/lib.sh` for the shared plumbing
(volatility, expected-file I/O, count comparison, the dedupe cache):

| Script | Engine | Expected files |
| --- | --- | --- |
| `run.sh` | PostgreSQL | `test/expected/` |
| `run-mysql.sh` | MySQL | `test/expected/mysql/` |
| `run-cockroach.sh` | CockroachDB | `test/expected/cockroach/` |
| `run-sqlite.sh` | SQLite | `test/expected/sqlite/` |
| `run-duckdb.sh` | DuckDB | `test/expected/duckdb/` |

Each script takes `<tag> <datasets-csv>` and, for every dataset in the image,
asserts that the set of base tables exactly matches the expected set (no missing
tables, no unexpected extras) and that `SELECT count(*)` on each table matches
the expected count. `REPOSITORY` overrides the image repository.

The three server engines boot a container and wait for it to be genuinely ready
before querying, so no half-loaded database is measured: PostgreSQL waits for
TCP readiness (a socket-only check returns ready mid-init), while MySQL and
CockroachDB first wait for an init-complete marker in the container log — via
lib.sh's `wait_for_log_marker`, which also fails fast if the container dies —
and then for the client to answer. That wait is one wall-clock budget, not an
iteration count: **`READY_TIMEOUT`** (default `300`, seconds) sets it, and on a
slow or emulated runner it is the knob to raise. On a timeout the script dumps
the tail of the container log. SQLite and DuckDB are serverless — the
database is a file baked into the image — so they boot nothing; `run-sqlite.sh`
instead gates on `PRAGMA quick_check` before counting, so a truncated or corrupt
database file fails as corruption rather than as a row-count mismatch. DuckDB
has no cheap equivalent, so `run-duckdb.sh` relies on the count pass itself: an
unopenable database yields zero tables, which lib.sh reports as one clear
"no tables found" line rather than a wall of missing-table errors.

### Expected files and floors

Expectations live per-dataset as JSON, keyed by qualified table name, e.g.
`test/expected/iso3166.json`:

```json
{
  "public.country": 242,
  "public.subcountry": 3995
}
```

A value is either a number (assert `count(*)` equals it exactly) or a floor like
`">=59274"` (assert `count(*) >=` it). Floors exist for datasets whose data is
fetched from a live upstream at build time and so drifts between builds. A
dataset is treated as volatile when it is named in the script's
`VOLATILE_DATASETS` (`omdb`, `moma`, `geonames`, `openflights`, per engine) or
when the tag matches `VOLATILE_TAG_PREFIXES` — `stackexchange-`, which covers
every StackExchange site by prefix, so adding a site needs no edit there.

To regenerate an expected file after an intentional dataset change, run the
script in update mode against a freshly built image. `--update` writes floors
for volatile datasets and exact counts for the rest, so the distinction is never
hand-maintained:

```sh
test/integration/run.sh --update iso3166 iso3166        # <tag> <datasets-csv>
test/integration/run-sqlite.sh --update geonames geonames
```

### Identical-image dedupe

Some tags are a second name for the same build, so a full `dave test` would boot
and assert the same image ID more than once. What a container does is a pure
function of its image, so once an image ID has passed a given set of
expectations, the run is skipped. The cache stamp holds the dataset list plus
the bytes of every expected file the run reads — two tags sharing an image but
asserting different datasets both still run, and editing an expected file
invalidates the stamp instead of silently skipping. Only clean assert runs write
a stamp; `--update` neither reads nor writes one.

* **`DDS_DEDUPE=0`** opts out entirely.
* **`DDS_TEST_CACHE`** sets the cache directory (default
  `${TMPDIR:-/tmp}/docker-dataset-itest`), so a stale entry cannot outlive a
  reboot.

## Running them

The integration scripts need `docker` and `jq` on the host; the database clients
run inside the containers.

```sh
brew install container-structure-test jq     # one-time
pip install -r test/requirements-dev.txt

python -m pytest test/unit -q                # unit tests (no Docker)
dave build
dave structure-test                          # static checks
dave test                                    # live smoke tests (boots images)

# scope to specific tags locally (note: -c <context> is required with -t):
dave test -c postgres -t iso3166 -t dellstore
```

[cst]: https://github.com/GoogleContainerTools/container-structure-test
