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

REPOSITORY="${REPOSITORY:-aa8y/sqlite-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count. Mirrors the other
# run scripts.
VOLATILE_DATASETS="moma"
VOLATILE_TAG_PREFIXES="stackexchange-"
is_volatile() {
  local db="$1"
  case " $VOLATILE_DATASETS " in *" $db "*) return 0 ;; esac
  local prefix
  for prefix in $VOLATILE_TAG_PREFIXES; do
    case "$TAG" in "$prefix"*) return 0 ;; esac
  done
  return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_DIR="${SCRIPT_DIR}/../expected/sqlite"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; }

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
    keyesc="${t//\'/\'\'}"         # escape embedded single quotes (string literal)
    [[ "$first" -eq 0 ]] && sql+=" UNION ALL "
    sql+="SELECT '${db}.${keyesc}' AS k, count(*) AS n FROM \"${esc}\""
    first=0
  done <<<"$tables"

  if [[ -z "$sql" ]]; then printf '{}\n'; return; fi
  # Output `<key>|<count>` rows, then fold into a JSON object.
  sqlite_q "$db" "$sql" | jq -R -s 'split("\n") | map(select(length>0) | split("|")) | map({(.[0]): (.[1]|tonumber)}) | add // {}'
}

rc=0
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"
for db in "${DATASETS[@]}"; do
  info "==> ${IMAGE} (${db})"
  expected_file="${EXPECTED_DIR}/${db}.json"
  actual="$(actual_counts "$db")"

  if [[ "$UPDATE" -eq 1 ]]; then
    mkdir -p "$EXPECTED_DIR"
    if is_volatile "$db"; then
      printf '%s\n' "$actual" | jq -S 'map_values(">=" + tostring)' > "$expected_file"
    else
      printf '%s\n' "$actual" | jq -S . > "$expected_file"
    fi
    pass "${db}: wrote $(jq 'length' <<<"$actual") tables to expected/sqlite/${db}.json"
    continue
  fi

  if [[ ! -f "$expected_file" ]]; then
    fail "${db}: missing expected file ${expected_file} (run with --update to create)"
    rc=1; continue
  fi
  expected="$(cat "$expected_file")"

  missing="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($e|keys_unsorted) - ($a|keys_unsorted) | .[]')"
  extra="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($a|keys_unsorted) - ($e|keys_unsorted) | .[]')"
  mismatch="$(jq -rn --argjson e "$expected" --argjson a "$actual" '
    ($e|keys_unsorted) as $ek
    | ($ek - ($ek - ($a|keys_unsorted)))[] as $k
    | $e[$k] as $ev | $a[$k] as $av
    | if ($ev|type) == "number" then
        (if $av != $ev then "\($k): expected \($ev) got \($av)" else empty end)
      else
        ($ev | capture("^(?<op>>=|>)(?<n>[0-9]+)$")) as $m
        | if $m == null then "\($k): invalid expected spec \"\($ev)\""
          else ($m.n | tonumber) as $n
            | if   ($m.op == ">"  and $av >  $n) then empty
              elif ($m.op == ">=" and $av >= $n) then empty
              else "\($k): expected \($ev) got \($av)" end
          end
      end')"

  db_ok=1
  if [[ -n "$missing" ]]; then
    db_ok=0; while IFS= read -r t; do fail "${db}: missing table ${t}"; done <<<"$missing"
  fi
  if [[ -n "$extra" ]]; then
    db_ok=0; while IFS= read -r t; do fail "${db}: unexpected table ${t}"; done <<<"$extra"
  fi
  if [[ -n "$mismatch" ]]; then
    db_ok=0; while IFS= read -r m; do fail "${db}: count mismatch ${m}"; done <<<"$mismatch"
  fi

  if [[ "$db_ok" -eq 1 ]]; then
    pass "${db}: $(jq 'length' <<<"$expected") tables present with matching counts"
  else
    rc=1
  fi
done

exit "$rc"
