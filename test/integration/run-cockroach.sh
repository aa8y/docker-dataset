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

REPOSITORY="${REPOSITORY:-aa8y/cockroach-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
#
# Mirrors run.sh / run-mysql.sh: volatility is detected two ways so we don't
# hand-maintain a flat list.
VOLATILE_DATASETS=""
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
EXPECTED_DIR="${SCRIPT_DIR}/../expected/cockroach"
CONTAINER="cr-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; }

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

crdb_q() {
  # crdb_q <db> <args...> — run `cockroach sql` (insecure) against <db> in the
  # test container with TSV output and the header row stripped.
  local db="$1"; shift
  docker exec "$CONTAINER" cockroach sql --insecure --database="$db" --format=tsv "$@" 2>/dev/null | tail -n +2
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by <schema>.<table>. List the base tables then run an actual count(*)
# per table and assemble the object with jq.
actual_counts() {
  local db="$1" rows s t n json='{}'
  rows="$(crdb_q "$db" -e "SELECT table_schema, table_name FROM information_schema.tables \
    WHERE table_type='BASE TABLE' \
      AND table_schema NOT IN ('pg_catalog','information_schema','crdb_internal') \
    ORDER BY table_schema, table_name")"
  while IFS=$'\t' read -r s t; do
    [[ -z "$t" ]] && continue
    n="$(crdb_q "$db" -e "SELECT count(*) FROM \"${s}\".\"${t}\"")"
    json="$(jq --arg k "${s}.${t}" --argjson v "${n:-0}" '. + {($k): $v}' <<<"$json")"
  done <<<"$rows"
  printf '%s\n' "$json"
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for initialisation to finish, then for the server to accept connections.
# The cockroach.sh entrypoint starts a node that already listens for SQL while
# it runs the init scripts against it, so a bare `SELECT 1` can succeed mid-init
# (we would then query half-loaded databases). The entrypoint prints
# "end running init files from /docker-entrypoint-initdb.d" only after every
# init script has run and just before it brings the server to the foreground --
# so we wait for that marker first, then for a successful query.
ready=0
for _ in $(seq 1 180); do
  if docker logs "$CONTAINER" 2>&1 | grep -q "end running init files"; then
    ready=1; break
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]]; then
    break
  fi
  sleep 1
done
if [[ "$ready" -eq 1 ]]; then
  ready=0
  for _ in $(seq 1 60); do
    if docker exec "$CONTAINER" cockroach sql --insecure -e "SELECT 1" >/dev/null 2>&1; then
      ready=1; break
    fi
    sleep 1
  done
fi
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: CockroachDB did not become ready in time"
  docker logs "$CONTAINER" 2>&1 | tail -40 >&2
  exit 1
fi

rc=0
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"
for db in "${DATASETS[@]}"; do
  expected_file="${EXPECTED_DIR}/${db}.json"
  actual="$(actual_counts "$db")"

  if [[ "$UPDATE" -eq 1 ]]; then
    mkdir -p "$EXPECTED_DIR"
    if is_volatile "$db"; then
      printf '%s\n' "$actual" | jq -S 'map_values(">=" + tostring)' > "$expected_file"
    else
      printf '%s\n' "$actual" | jq -S . > "$expected_file"
    fi
    pass "${db}: wrote $(jq 'length' <<<"$actual") tables to expected/cockroach/${db}.json"
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
