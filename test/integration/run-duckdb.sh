#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/duckdb-dataset image.
#
# DuckDB is embedded, like SQLite -- a database is just a file baked into the
# image -- so, as in run-sqlite.sh, there is no server to boot or wait for. For
# each dataset (= database file) shipped in the image this asserts that:
#   1. the set of tables present exactly matches the expected set
#      (no missing tables, no unexpected extras; views are not counted), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/duckdb/<dataset>.json, e.g.
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
#   run-duckdb.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-duckdb.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-duckdb.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-duckdb.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/duckdb-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds: the MoMA CSVs and the StackExchange dumps
# are both refreshed in place. Same knobs as the other run scripts.
VOLATILE_DATASETS="moma"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="duckdb"
. "${SCRIPT_DIR}/lib.sh"

# Identical-image dedupe: some tags are just a second name for the same build,
# and what a container does is a pure function of its image -- here quite
# literally, the database is a file baked into it. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

duckdb_q() {
  # duckdb_q <db> <sql> — run a query against /data/<db>.duckdb in a throwaway
  # container, returning header-less CSV rows. The image is distroless with no
  # ENTRYPOINT, so these arguments replace the CMD outright and must name the
  # binary by absolute path: docker execs /duckdb directly, no shell involved.
  # -readonly keeps a query from ever mutating the shipped file.
  local db="$1" sql="$2"
  docker run --rm "$IMAGE" /duckdb -readonly -csv -noheader -c "$sql" "/data/${db}.duckdb"
}

# Authoritative counts for every table in a database, as a JSON object keyed by
# <db>.<table>. List the user tables (excluding views and system catalogs),
# then count every row with a single UNION ALL query and assemble the object
# with jq.
actual_counts() {
  # Table list via information_schema rather than duckdb_tables(): the
  # information_schema view already hides DuckDB's internal catalogs (no
  # `internal` flag to filter on), and table_schema='main' scopes it to the
  # attached database file while table_type excludes views.
  local db="$1" tables t esc keyesc sql first=1
  tables="$(duckdb_q "$db" "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name")"
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
  # Output `<key>,<count>` rows (CSV mode), then fold into a JSON object.
  duckdb_q "$db" "$sql" | counts_to_json ','
}

# No corruption gate before counting: DuckDB has no analog of SQLite's cheap
# PRAGMA quick_check. Opening the file already validates its header, and the
# count pass touches every table, so a truncated or unreadable database fails
# loudly in actual_counts (an open error yields zero tables, which the
# "no tables found" branch of check_counts reports) rather than passing silently.

# Assertion outcomes below are deterministic -- same image, same expected bytes,
# same verdict -- so they exit $ASSERT_RC, which with-retry.sh never retries.
rc=0
for db in "${DATASETS[@]}"; do
  info "==> ${IMAGE} (${db})"
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
