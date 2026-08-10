#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/cockroach-dataset image.
#
# The CockroachDB counterpart of run.sh / run-mysql.sh. Boots the image, waits
# for the single node to accept SQL connections (all init scripts have run by
# then), then for each dataset (= database) shipped in the image asserts that:
#   1. the set of base tables present exactly matches the expected set
#      (no missing tables, no unexpected extras), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/cockroach/<dataset>.json, e.g.
#
#     { "public.Album": 347, "public.Artist": 275, ... }
#
# keyed by <schema>.<table> (CockroachDB puts a dataset's tables in the `public`
# schema of its database, mirroring the postgres expected files). Counts are
# authoritative count(*). A value can be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds.
#
# Usage:
#   run-cockroach.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-cockroach.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-cockroach.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-cockroach.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/cockroach-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
#
# Mirrors run.sh / run-mysql.sh: volatility is detected two ways so we don't
# hand-maintain a flat list.
VOLATILE_DATASETS="geonames openflights"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="cockroach"
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="cr-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

crdb_q() {
  # crdb_q <db> <args...> — run `cockroach sql` (insecure) against <db> in the
  # test container with TSV output and the header row stripped.
  local db="$1"; shift
  docker exec "$CONTAINER" cockroach sql --insecure --database="$db" --format=tsv "$@" 2>/dev/null | tail -n +2
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by <schema>.<table>. List the base tables from information_schema and
# then count them all in a single generated UNION ALL query -- two `cockroach
# sql` round-trips and one jq fold for the whole database, however many tables
# it has. Counting one table per `docker exec` instead pays a container-exec
# plus cockroach-client cold start every time, which on the wider datasets
# (sportsdb ships 107 tables) dominates the run.
actual_counts() {
  local db="$1" rows s t sesc tesc keyesc sql first=1
  rows="$(crdb_q "$db" -e "SELECT table_schema, table_name FROM information_schema.tables \
    WHERE table_type='BASE TABLE' \
      AND table_schema NOT IN ('pg_catalog','information_schema','crdb_internal') \
    ORDER BY table_schema, table_name")"
  sql=""
  while IFS=$'\t' read -r s t; do
    [[ -z "$t" ]] && continue
    sesc="${s//\"/\"\"}"           # escape embedded double quotes (identifiers)
    tesc="${t//\"/\"\"}"
    keyesc="$(sql_squote "$s").$(sql_squote "$t")"  # ... and single quotes (literal)
    [[ "$first" -eq 0 ]] && sql+=" UNION ALL "
    sql+="SELECT '${keyesc}' AS k, count(*) AS n FROM \"${sesc}\".\"${tesc}\""
    first=0
  done <<<"$rows"

  if [[ -z "$sql" ]]; then printf '{}\n'; return; fi
  # Output `<key>\t<count>` rows, then fold into a JSON object. Note that
  # --format=tsv quotes a field that itself contains a tab, newline or quote;
  # every dataset's keys are plain identifiers, so they pass through raw.
  crdb_q "$db" -e "$sql" | counts_to_json $'\t'
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for initialisation to finish, then for the server to accept connections.
# The cockroach.sh entrypoint starts a node that already listens for SQL while
# it runs the init scripts against it, so a bare `SELECT 1` can succeed mid-init
# (we would then query half-loaded databases). The entrypoint prints
# "end running init files from /docker-entrypoint-initdb.d" only after every
# init script has run and just before it brings the server to the foreground --
# so we wait for that marker first, then for a successful query. (CockroachDB is
# by far the chattiest of these servers, which is what makes the single-stream
# marker watch in lib.sh matter most here.)
#
# Both phases share one wall-clock deadline, not a fixed iteration count: each
# `docker exec` round-trip on a loaded ARM runner can itself take a second or
# more, so an N-iteration loop silently waits far less than N seconds. One budget
# rather than two also means a marker wait that only just squeaked in can't then
# be granted a fresh 60s to answer a query. 300s matches the Postgres/MySQL
# budgets; the largest inits (dellstore, usda, stackexchange, moma, sportsdb) can
# exceed the old 180-count loop on CRDB.
READY_TIMEOUT="${READY_TIMEOUT:-300}"
deadline=$(( SECONDS + READY_TIMEOUT ))
ready=0
if wait_for_log_marker "end running init files" "$deadline"; then
  while (( SECONDS < deadline )); do
    if docker exec "$CONTAINER" cockroach sql --insecure -e "SELECT 1" >/dev/null 2>&1; then
      ready=1; break
    fi
    sleep 1
  done
fi
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: CockroachDB did not become ready in time (${READY_TIMEOUT}s)"
  docker logs "$CONTAINER" 2>&1 | tail -40 >&2
  exit 1
fi

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
    rc=1; continue
  fi

  check_counts "$db" "$(cat "$expected_file")" "$actual" || rc=1
done

record_pass_stamp "$rc"
exit "$rc"
