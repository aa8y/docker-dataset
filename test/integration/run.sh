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
#                  drifts between builds (omdb, moma, and any `stackexchange-`
#                  tagged site, whose archive.org dump is refreshed over time).
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
VOLATILE_DATASETS="omdb moma"
VOLATILE_TAG_PREFIXES="stackexchange-"
is_volatile() {
  # is_volatile <db> — true if this dataset's counts drift between builds,
  # either because the dataset is explicitly listed or because $TAG matches a
  # volatile prefix (each image carries a single dataset, so the tag decides).
  local db="$1"
  case " $VOLATILE_DATASETS " in *" $db "*) return 0 ;; esac
  local prefix
  for prefix in $VOLATILE_TAG_PREFIXES; do
    case "$TAG" in "$prefix"*) return 0 ;; esac
  done
  return 1
}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_DIR="${SCRIPT_DIR}/../expected"
CONTAINER="pg-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

# All human-readable logging goes to stderr, which keeps stdout free for
# machine-readable output (`dave test` streams both live). Diagnostics staying
# on stderr is also what keeps CI failures -- which tables/counts mismatched --
# legible when stdout is being piped or captured.
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; }

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe. Some tags are just a second name for the same build --
# `latest` is built from the same inputs as `world` -- so a full `dave test` can
# boot and assert the very same image ID more than once. What a container does is
# a pure function of its image, so once an image ID has passed a given set of
# expectations there is nothing left to learn from booting it again.
#
# "a given set of expectations" is the point of the stamp: it holds the dataset
# list plus the bytes of every expected/*.json this run reads, so two tags that
# share an image but assert different datasets still both run, and editing an
# expected file invalidates the entry rather than silently skipping past it.
# Only a clean assert run writes a stamp -- a failure has to stay reproducible --
# --update neither reads nor writes one, and DDS_DEDUPE=0 opts out entirely. The
# cache lives under an ephemeral tmp dir, so a stale entry cannot outlive a boot.
CACHE_DIR="${DDS_TEST_CACHE:-${TMPDIR:-/tmp}/docker-dataset-itest}"
stamp_file=""

stamp_contents() {
  local db
  printf '%s\n' "$DATASETS_CSV"
  for db in "${DATASETS[@]}"; do
    cat "${EXPECTED_DIR}/${db}.json" 2>/dev/null || true
  done
}

if [[ "$UPDATE" -eq 0 && "${DDS_DEDUPE:-1}" != "0" ]]; then
  # An image we cannot resolve locally is simply not deduped; `docker run` below
  # will pull it as before.
  image_id="$(docker image inspect -f '{{.Id}}' "$IMAGE" 2>/dev/null || true)"
  if [[ -n "$image_id" ]]; then
    mkdir -p "$CACHE_DIR"
    stamp_file="${CACHE_DIR}/${image_id//[^a-zA-Z0-9]/-}"
    if [[ -f "$stamp_file" ]] && stamp_contents | cmp -s - "$stamp_file"; then
      short_id="${image_id#sha256:}"
      pass "${IMAGE}: identical image (${short_id:0:12}) already passed as an earlier tag; skipping"
      exit 0
    fi
  fi
fi

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
  exit 1
fi

rc=0
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
  # Count check on tables present in both: a number means exact match, a
  # ">=N" / ">N" string means a floor.
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

# Record the pass, so a later tag resolving to this same image ID with these same
# expectations can skip the boot entirely. Clean runs only ($stamp_file is empty
# in --update mode and when dedupe is off).
if [[ "$rc" -eq 0 && -n "$stamp_file" ]]; then
  stamp_contents > "$stamp_file"
fi

exit "$rc"
