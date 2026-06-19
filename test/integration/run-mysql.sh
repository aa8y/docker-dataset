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
#                  between builds (moma).
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

REPOSITORY="${REPOSITORY:-aa8y/mysql-dataset}"
IMAGE="${REPOSITORY}:${TAG}"
ROOT_PW="${MYSQL_ROOT_PASSWORD:-mysql}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count.
VOLATILE_DATASETS="moma"
is_volatile() {
  local db="$1"
  case " $VOLATILE_DATASETS " in *" $db "*) return 0 ;; esac
  return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_DIR="${SCRIPT_DIR}/../expected/mysql"
CONTAINER="my-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s\u2713%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s\u2717%s %s\n' "$RED" "$RESET" "$*" >&2; }

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

mysql_q() {
  # mysql_q <args...> — run the mariadb client in the test container, returning
  # tab-separated, header-less rows.
  docker exec "$CONTAINER" mariadb -uroot -p"$ROOT_PW" -N -B "$@" 2>/dev/null
}

# Authoritative counts for every base table in a database, as a JSON object
# keyed by <db>.<table>. MariaDB has no query_to_xml, so we list the base
# tables then run an actual count(*) per table and assemble the object with jq.
actual_counts() {
  local db="$1" tables t n json='{}'
  tables="$(mysql_q -e "SELECT table_name FROM information_schema.tables \
    WHERE table_type='BASE TABLE' AND table_schema='${db}' ORDER BY table_name")"
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    n="$(mysql_q -e "SELECT COUNT(*) FROM \`${db}\`.\`${t}\`")"
    json="$(jq --arg k "${db}.${t}" --argjson v "${n:-0}" '. + {($k): $v}' <<<"$json")"
  done <<<"$tables"
  printf '%s\n' "$json"
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for initialisation to finish, then for the server to accept connections.
# The MariaDB entrypoint runs the init scripts against a temporary server (also
# reachable on the socket), so a bare ping can succeed mid-init. It prints
# "Ready for start up." only after every init script has run and just before it
# execs the real server -- so we wait for that marker first, then for ping.
ready=0
for _ in $(seq 1 180); do
  if docker logs "$CONTAINER" 2>&1 | grep -q "Ready for start up"; then
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
    if docker exec "$CONTAINER" mariadb-admin -uroot -p"$ROOT_PW" ping >/dev/null 2>&1; then
      ready=1; break
    fi
    sleep 1
  done
fi
if [[ "$ready" -ne 1 ]]; then
  fail "${IMAGE}: MariaDB did not become ready in time"
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
    pass "${db}: wrote $(jq 'length' <<<"$actual") tables to expected/mysql/${db}.json"
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
