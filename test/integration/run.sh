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
# not the approximate pg_stat n_live_tup.
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

REPOSITORY="${REPOSITORY:-aa8y/postgres-dataset}"
IMAGE="${REPOSITORY}:${TAG}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_DIR="${SCRIPT_DIR}/../expected"
CONTAINER="pg-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

# All human-readable logging goes to stderr. `dave test` runs this via
# child_process.exec and discards a command's stdout, surfacing only stderr
# when the command fails -- so routing diagnostics to stderr keeps CI
# failures (which tables/counts mismatched) visible.
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; }

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

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
ready=0
for _ in $(seq 1 120); do
  if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: Postgres did not become ready in time"
  docker logs "$CONTAINER" 2>&1 | tail -30 >&2
  exit 1
fi

rc=0
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"
for db in "${DATASETS[@]}"; do
  expected_file="${EXPECTED_DIR}/${db}.json"
  actual="$(actual_counts "$db")"

  if [[ "$UPDATE" -eq 1 ]]; then
    mkdir -p "$EXPECTED_DIR"
    printf '%s\n' "$actual" | jq -S . > "$expected_file"
    pass "${db}: wrote $(jq 'length' <<<"$actual") tables to expected/${db}.json"
    continue
  fi

  if [[ ! -f "$expected_file" ]]; then
    fail "${db}: missing expected file ${expected_file} (run with --update to create)"
    rc=1; continue
  fi
  expected="$(cat "$expected_file")"

  # Table-set diff: keys present in one side but not the other.
  missing="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($e|keys_unsorted) - ($a|keys_unsorted) | .[]')"
  extra="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($a|keys_unsorted) - ($e|keys_unsorted) | .[]')"
  # Count mismatches on tables present in both.
  mismatch="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($e|keys_unsorted) as $ek | $ek - (($ek) - ($a|keys_unsorted))
     | map(select($e[.] != $a[.]) | "\(.): expected \($e[.]) got \($a[.])") | .[]')"

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
