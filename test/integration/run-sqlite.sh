#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/sqlite-dataset image.
#
# SQLite is serverless -- a database is just a file baked into the image -- so
# unlike run.sh / run-mysql.sh / run-cockroach.sh there is no server to boot or
# wait for. For each dataset (= database file) shipped in the image this asserts
# that:
#   1. the set of tables present exactly matches the expected set
#      (no missing tables, no unexpected extras; views are not counted), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/sqlite/<dataset>.json, e.g.
#
#     { "chinook.Album": 347, "chinook.Track": 3503, ... }
#
# keyed by <database>.<table> (the database name is the dataset / file base
# name). Counts are authoritative count(*). A value can be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds.
#
# Usage:
#   run-sqlite.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-sqlite.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-sqlite.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-sqlite.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/sqlite-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count. Mirrors the other
# run scripts.
VOLATILE_DATASETS="moma"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="sqlite"
. "${SCRIPT_DIR}/lib.sh"

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image -- here quite literally, the database is a file baked into it. See
# lib.sh for the stamp semantics.
if dedupe_skip; then exit 0; fi

sqlite_q() {
  # sqlite_q <db> <sql> — run a query against /data/<db>.db in a throwaway
  # container, returning pipe-free, header-less rows (default sqlite3 list mode).
  local db="$1" sql="$2"
  docker run --rm "$IMAGE" /usr/bin/sqlite3 "/data/${db}.db" "$sql"
}

# Authoritative counts for every table in a database, as a JSON object keyed by
# <db>.<table>. List the user tables (excluding sqlite internal tables and
# views), then count every row with a single UNION ALL query and assemble the
# object with jq.
actual_counts() {
  local db="$1" tables t esc keyesc sql first=1
  tables="$(sqlite_q "$db" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")"
  sql=""
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    esc="${t//\"/\"\"}"            # escape embedded double quotes (identifier)
    keyesc="$(sql_squote "$t")"    # escape embedded single quotes (string literal)
    [[ "$first" -eq 0 ]] && sql+=" UNION ALL "
    sql+="SELECT '${db}.${keyesc}' AS k, count(*) AS n FROM \"${esc}\""
    first=0
  done <<<"$tables"

  if [[ -z "$sql" ]]; then printf '{}\n'; return; fi
  # Output `<key>|<count>` rows, then fold into a JSON object.
  sqlite_q "$db" "$sql" | counts_to_json '|'
}

integrity_ok() {
  # integrity_ok <db> — cheap corruption gate, run before counting (in --update
  # mode too, so expectations are never recorded from a damaged artifact).
  # PRAGMA quick_check walks every table btree and prints exactly "ok" for a
  # sound file, or a list of problems for a truncated or corrupt one -- damage
  # that row counts alone can miss. It skips integrity_check's expensive
  # index-content verification, so it costs about a second per dataset. A
  # database sqlite cannot open at all prints its error on stderr and yields
  # no stdout, which the empty-result message below covers; that is a fact
  # about this one dataset file, not the run, so it must not abort the script.
  local db="$1" result
  result="$(sqlite_q "$db" "PRAGMA quick_check")" || true
  if [[ "$result" != "ok" ]]; then
    fail "${db}: PRAGMA quick_check failed: ${result:-no output (unreadable database?)}"
    return 1
  fi
}

rc=0
for db in "${DATASETS[@]}"; do
  info "==> ${IMAGE} (${db})"
  integrity_ok "$db" || { rc=1; continue; }
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
