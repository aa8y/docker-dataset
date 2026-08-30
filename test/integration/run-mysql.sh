#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/mysql-dataset image.
#
# The MySQL counterpart of run.sh. Boots the image, waits for the MariaDB
# entrypoint to finish initialising and the server to accept connections, then
# for each dataset (= database) shipped in the image asserts that:
#   1. the set of base tables present exactly matches the expected set
#      (no missing tables, no unexpected extras), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/mysql/<dataset>.json, e.g.
#
#     { "world.city": 4079, "world.country": 239, "world.countrylanguage": 984 }
#
# keyed by <database>.<table>. Counts are authoritative count(*). A value can
# be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds (moma, geonames, openflights).
#
# Usage:
#   run-mysql.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-mysql.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-mysql.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-mysql.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/mysql-dataset}"
IMAGE="${REPOSITORY}:${TAG}"
ROOT_PW="${MYSQL_ROOT_PASSWORD:-mysql}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
#
# Mirrors run.sh: volatility is detected two ways so we don't hand-maintain a
# flat list:
#   * VOLATILE_DATASETS - explicit per-dataset names (one-off live sources), and
#   * VOLATILE_TAG_PREFIXES - tag prefixes whose datasets are all volatile. Every
#     StackExchange site ships under a `stackexchange-` tag and is built from a
#     periodically refreshed archive.org dump, so the whole family is volatile
#     by prefix and a new site needs no edit here.
VOLATILE_DATASETS="moma geonames openflights"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="mysql"
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="my-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

mysql_q() {
  # mysql_q <args...> — run the mariadb client in the test container, returning
  # tab-separated, header-less rows.
  docker exec "$CONTAINER" mariadb -uroot -p"$ROOT_PW" -N -B "$@" 2>/dev/null
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by <db>.<table>. MariaDB has no query_to_xml, so we list the base tables
# from information_schema and then count them all in a single generated
# UNION ALL query -- two client round-trips and one jq fold for the whole
# database, however many tables it has. Counting one table per `docker exec`
# instead pays a container-exec plus mariadb-client cold start every time, which
# on the wider datasets (sportsdb ships 107 tables) dominates the run.
actual_counts() {
  local db="$1" tables t esc keyesc sql first=1
  tables="$(mysql_q -e "SELECT table_name FROM information_schema.tables \
    WHERE table_type='BASE TABLE' AND table_schema='${db}' ORDER BY table_name")"
  sql=""
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    esc="${t//\`/\`\`}"            # escape embedded backticks (identifier)
    keyesc="$(sql_squote "$t")"    # escape embedded single quotes (string literal)
    [[ "$first" -eq 0 ]] && sql+=" UNION ALL "
    sql+="SELECT '${db}.${keyesc}' AS k, COUNT(*) AS n FROM \`${db}\`.\`${esc}\`"
    first=0
  done <<<"$tables"

  if [[ -z "$sql" ]]; then printf '{}\n'; return; fi
  # Output `<key>\t<count>` rows (mariadb -N -B is header-less TSV), then fold
  # into a JSON object.
  mysql_q -e "$sql" | counts_to_json $'\t'
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for initialisation to finish, then for the server to accept connections.
# The MariaDB entrypoint runs the init scripts against a temporary server (also
# reachable on the socket), so a bare ping can succeed mid-init. It prints
# "Ready for start up." only after every init script has run and just before it
# execs the real server -- so we wait for that marker first, then for ping.
#
# Both phases share one wall-clock budget, not a fixed iteration count: an
# iteration costs a `docker exec` round-trip, which on a loaded ARM runner can
# itself take a second or more, so an N-iteration loop silently waits far less
# than N seconds. 300s matches the Postgres/CockroachDB budgets. The marker wait
# has to cover the full init-script import, which for the larger INSERT-based
# datasets (sportsdb) is the slow part and runs noticeably slower on CI runners
# than locally. conf/zz-dataset-fast-import.cnf cuts that time, but we still
# allow a generous budget here so a slow runner doesn't spuriously fail.
READY_TIMEOUT="${READY_TIMEOUT:-300}"
deadline=$(( SECONDS + READY_TIMEOUT ))
ready=0
if wait_for_log_marker "Ready for start up" "$deadline"; then
  while (( SECONDS < deadline )); do
    if docker exec "$CONTAINER" mariadb-admin -uroot -p"$ROOT_PW" ping >/dev/null 2>&1; then
      ready=1; break
    fi
    sleep 1
  done
fi
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: MariaDB did not become ready in time (${READY_TIMEOUT}s)"
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
