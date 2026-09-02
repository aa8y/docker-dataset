#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/clickhouse-dataset image.
#
# The ClickHouse counterpart of run.sh / run-mysql.sh / run-cockroach.sh. Boots
# the image, waits for the post-init server to accept queries (all init scripts
# have run by then), then for each dataset (= database) shipped in the image
# asserts that:
#   1. the set of base tables present exactly matches the expected set
#      (no missing tables, no unexpected extras; views are not counted), and
#   2. SELECT count() on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/clickhouse/<dataset>.json, e.g.
#
#     { "world.city": 4079, "world.country": 239, ... }
#
# keyed by <database>.<table> (ClickHouse's "database" is the whole namespace --
# there is no schema level below it -- so the key is the dataset name and the
# table name, mirroring the mysql expected files). Counts are authoritative
# count(). A value can be either:
#   - a number  -> assert count() == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count() >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds.
#
# Usage:
#   run-clickhouse.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-clickhouse.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-clickhouse.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-clickhouse.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/clickhouse-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
#
# Mirrors the other run scripts: volatility is detected two ways so we don't
# hand-maintain a flat list -- explicit dataset names for the one-off live
# sources, and a tag prefix for the whole StackExchange family (every site is
# built from a periodically refreshed archive.org dump, so adding a site needs
# no edit here).
VOLATILE_DATASETS="moma geonames openflights"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="clickhouse"
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="ch-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

# `-v` as well as `-f`: /var/lib/clickhouse is a VOLUME in the base image, so
# every `docker run` here creates an anonymous volume holding the whole loaded
# database. Without -v those survive the container and pile up -- a few hundred
# MB per tag per run, which on a laptop running the suite repeatedly is the
# difference between a working Docker disk and a full one.
cleanup() { docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `nyc-taxi`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

ch_q() {
  # ch_q <sql> — run one query with clickhouse-client in the test container,
  # returning the raw rows (TSV, header-less, which is the client's default).
  docker exec "$CONTAINER" clickhouse-client --query "$1" 2>/dev/null
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by <db>.<table>. List the tables from system.tables and then count them
# all in a single generated UNION ALL query -- two `docker exec` round-trips and
# one jq fold for the whole database, however many tables it has. Counting one
# table per exec instead pays a container-exec plus client cold start every
# time, which on the wider datasets dominates the run.
actual_counts() {
  local db="$1" tables t esc keyesc sql first=1
  # system.tables rather than information_schema: it is ClickHouse's own
  # catalog and carries the engine, which is how a view is excluded here --
  # View / MaterializedView / LiveView / WindowView all end in "View", and
  # every table these images create is a MergeTree.
  tables="$(ch_q "SELECT name FROM system.tables \
    WHERE database = '$(sql_squote "$db")' AND engine NOT LIKE '%View' \
    ORDER BY name")"
  sql=""
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    esc="${t//\`/\\\`}"                             # escape backticks (identifier)
    keyesc="$(sql_squote "$db").$(sql_squote "$t")" # ... and quotes (literal)
    [[ "$first" -eq 0 ]] && sql+=" UNION ALL "
    sql+="SELECT '${keyesc}' AS k, count() AS n FROM \`${db}\`.\`${esc}\`"
    first=0
  done <<<"$tables"

  if [[ -z "$sql" ]]; then printf '{}\n'; return; fi
  # Output `<key>\t<count>` rows (TSV is the client's default format), then
  # fold into a JSON object. TSV escapes a tab inside a value as \t, so a key
  # can never split a row; every dataset's keys are plain identifiers anyway.
  ch_q "$sql FORMAT TSV" | counts_to_json $'\t'
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for the *post-init* server. This needs care on ClickHouse, because the
# entrypoint runs the init scripts against a temporary server of its own -- one
# that answers on 127.0.0.1 only, deliberately, so nothing outside the container
# can see a half-loaded database. A `docker exec clickhouse-client` connects to
# 127.0.0.1 too, so the obvious readiness probe would succeed in the middle of
# the load and we would count a half-populated dataset.
#
# The distinguishing signal is therefore the listening address, not the query:
# only the real server (exec'd after every init script has run) binds the
# container's own interface, so we ping the HTTP port on the container's eth0
# address from inside. /ping needs no authentication and no client, and the
# address is refused outright while only the init server is up.
#
# Both phases share one wall-clock deadline, not a fixed iteration count: each
# `docker exec` round-trip on a loaded ARM runner can itself take a second or
# more, so an N-iteration loop silently waits far less than N seconds. 300s
# matches the Postgres/MySQL/CockroachDB budgets; the largest loads here
# (usda's 366k rows, the StackExchange sites, nyc-taxi's 4.3M-row Parquet) run
# well inside it locally but need the headroom on an emulated runner.
READY_TIMEOUT="${READY_TIMEOUT:-300}"
deadline=$(( SECONDS + READY_TIMEOUT ))
ready=0
while (( SECONDS < deadline )); do
  # `hostname -i` is resolved per attempt: the container may not have finished
  # starting on the first one, in which case the exec itself fails.
  if docker exec "$CONTAINER" sh -c \
      'wget -q -O - "http://$(hostname -i):8123/ping" 2>/dev/null | grep -q Ok' \
      >/dev/null 2>&1; then
    # The server is on all interfaces; make sure it also answers a real query
    # before anything is counted.
    if docker exec "$CONTAINER" clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
      ready=1; break
    fi
  fi
  # A container that died during init never becomes ready; fail fast rather
  # than burning the whole budget on a corpse.
  if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]]; then
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: ClickHouse did not become ready in time (${READY_TIMEOUT}s)"
  docker logs "$CONTAINER" 2>&1 | tail -40 >&2
  # Plain 1, deliberately not $ASSERT_RC: a readiness timeout is exactly the
  # kind of failure a loaded or emulated runner produces once and not again, so
  # it stays in the retryable class (see the contract in lib.sh).
  exit 1
fi

# Assertion outcomes below are deterministic -- same image, same expected bytes,
# same verdict -- so they exit $ASSERT_RC, which with-retry.sh never retries.
rc=0
for db in "${DATASETS[@]}"; do
  expected_file="${EXPECTED_DIR}/${db}.json"
  actual="$(actual_counts "$db")"

  if [[ "$UPDATE" -eq 1 ]]; then
    write_expected "$db" "$actual"
    continue
  fi

  if [[ ! -f "$expected_file" ]]; then
    fail "${db}: missing expected file ${expected_file} (run with --update to create)"
    rc="$ASSERT_RC"; continue
  fi

  check_counts "$db" "$(cat "$expected_file")" "$actual" || rc="$ASSERT_RC"
done

record_pass_stamp "$rc"
exit "$rc"
