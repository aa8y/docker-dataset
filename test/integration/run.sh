#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/postgres-dataset image.
#
# Boots the image, waits for Postgres to accept connections, then for each
# dataset (= database) shipped in the image asserts that:
#   1. the set of base tables present exactly matches the expected set
#      (no missing tables, no unexpected extras), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/<dataset>.json, e.g.
#
#     { "public.country": 242, "public.subcountry": 3995 }
#
# keyed by schema-qualified table name. Counts are authoritative count(*),
# not the approximate pg_stat n_live_tup. A value can be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose
#                  data is fetched from a live upstream at build time and so
#                  drifts between builds (omdb, moma, geonames, openflights,
#                  and any `stackexchange-` tagged site, whose archive.org dump
#                  is refreshed over time).
#
# Usage:
#   run.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
#
# <datasets-csv> is the comma-separated list of datasets baked into the
# image (the same DATASETS build arg / {{datasets}} manifest parameter), so
# `dave test` drives this script per tag with no duplicated tag list.
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/postgres-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
#
# Volatility is detected two ways so we don't hand-maintain a flat list:
#   * VOLATILE_DATASETS - explicit per-dataset names (one-off live sources), and
#   * VOLATILE_TAG_PREFIXES - tag prefixes whose datasets are all volatile. Every
#     StackExchange site ships under a `stackexchange-` tag and is built from a
#     periodically refreshed archive.org dump, so the whole family is volatile
#     by prefix and a new site needs no edit here.
VOLATILE_DATASETS="omdb moma geonames openflights"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR=""   # postgres, the original engine, keeps test/expected/ un-nested
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="pg-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

psql_db() {
  # psql_db <db> <args...> — run psql against <db> in the test container.
  local db="$1"; shift
  docker exec "$CONTAINER" psql -U postgres -d "$db" -At "$@"
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by schema.table. query_to_xml runs an actual count(*) per table.
actual_counts() {
  local db="$1"
  psql_db "$db" -c "
    SELECT coalesce(json_object_agg(tbl, n ORDER BY tbl), '{}')
    FROM (
      SELECT table_schema || '.' || table_name AS tbl,
             (xpath('/row/cnt/text()',
                    query_to_xml(format('SELECT count(*) AS cnt FROM %I.%I',
                                        table_schema, table_name),
                                 false, true, '')))[1]::text::bigint AS n
      FROM information_schema.tables
      WHERE table_type = 'BASE TABLE'
        AND table_schema NOT IN ('pg_catalog', 'information_schema')
    ) t;"
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for Postgres to be ready. The official entrypoint runs every init
# script against a temporary server that listens on the unix socket only,
# then restarts the real server on TCP. So we must wait on a TCP connection
# (-h 127.0.0.1): a socket-only check returns ready mid-init and we would
# query half-loaded databases. TCP readiness means all init scripts (every
# database, fully populated) have completed.
#
# The budget is a wall-clock deadline, not a fixed iteration count: each
# pg_isready runs via `docker exec`, which on a loaded ARM runner can itself
# take a second or more, so an N-iteration loop silently waits far less than N
# seconds. 300s matches the MySQL budget; the heaviest dataset (sportsdb) loads
# well inside it on emulated/ARM runners but exceeded the old 120-count loop.
READY_TIMEOUT="${READY_TIMEOUT:-300}"
ready=0
deadline=$(( SECONDS + READY_TIMEOUT ))
while (( SECONDS < deadline )); do
  if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: Postgres did not become ready in time (${READY_TIMEOUT}s)"
  docker logs "$CONTAINER" 2>&1 | tail -30 >&2
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
