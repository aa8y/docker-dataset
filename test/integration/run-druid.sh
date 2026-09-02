#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/druid-dataset image.
#
# The Apache Druid counterpart of run-cockroach.sh. Boots the image, waits for
# the entrypoint's ready marker (which is only printed once every ingestion task
# has succeeded, every segment has loaded and every datasource answers SQL),
# then for each dataset shipped in the image asserts that:
#   1. the set of datasources present exactly matches the expected set
#      (no missing tables, no unexpected extras), and
#   2. SELECT count(*) on every datasource matches the expected row count.
#
# Druid has no databases: one image carries one dataset, and each of its tables
# becomes a datasource of the same name in the single `druid` schema. So the
# per-dataset loop below runs once, and expected keys are <dataset>.<table> --
# the same shape as the DuckDB files, where the prefix is likewise the dataset
# rather than anything the engine models.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/druid/<dataset>.json, e.g.
#
#     { "world.city": 4079, "world.country": 239, ... }
#
# Counts are authoritative count(*). A value can be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds.
#
# Usage:
#   run-druid.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-druid.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-druid.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-druid.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/druid-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. Same knobs as the other run scripts.
VOLATILE_DATASETS="moma geonames openflights"
VOLATILE_TAG_PREFIXES="stackexchange-"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="druid"
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="druid-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics. Worth more here than anywhere else in this repo -- a skipped Druid
# tag is a whole cluster boot and re-ingest not paid for.
if dedupe_skip; then exit 0; fi

druid_sql() {
  # druid_sql <sql> — POST one query to the router's SQL endpoint from inside
  # the container, printing the raw JSON array of result objects.
  #
  # From inside rather than through a published port: the image ships curl for
  # its own entrypoint, so `docker exec` needs no port mapping, no host-port
  # allocation and no guessing about which interface the daemon binds. jq (on
  # the host) does the parsing, exactly as it does for the other engines.
  local sql="$1"
  docker exec "$CONTAINER" curl -fsS -H 'Content-Type: application/json' \
    --data-binary "$(jq -n --arg q "$sql" '{query: $q}')" \
    http://localhost:8888/druid/v2/sql
}

# Authoritative counts for every datasource in the image, as a JSON object keyed
# by <dataset>.<table>. Unlike the SQL engines there is no UNION ALL shortcut
# worth taking: Druid answers `SELECT count(*) FROM a UNION ALL SELECT ...`
# only through its multi-stage engine, and a plain per-datasource count is a
# millisecond query against a single loaded segment. So the datasources are
# listed once and then counted one query at a time.
actual_counts() {
  local db="$1" tables t counts=""
  # INFORMATION_SCHEMA.TABLES is the broker's view of what is queryable; the
  # `druid` schema holds the datasources, while `sys`, `INFORMATION_SCHEMA` and
  # `lookup` hold Druid's own metadata tables.
  tables="$(druid_sql "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'druid' ORDER BY TABLE_NAME" |
    jq -r '.[].TABLE_NAME')"
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    # The datasource name is double-quoted as an identifier, with any embedded
    # double quote doubled -- the same escaping the other engines' scripts do.
    # Unlike them the expected-file key is assembled in the shell rather than
    # inside the query, so no string-literal escaping is needed for it.
    counts+="${db}.${t}"$'\t'"$(druid_sql "SELECT count(*) AS n FROM \"${t//\"/\"\"}\"" | jq -r '.[0].n')"$'\n'
  done <<<"$tables"

  if [[ -z "$counts" ]]; then printf '{}\n'; return; fi
  printf '%s' "$counts" | counts_to_json $'\t'
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for the entrypoint's ready marker. Unlike the other server engines there
# is nothing to poll *after* it: the marker is printed only once the entrypoint
# has itself confirmed every datasource answers a query, so a successful marker
# means the very assertions below can run immediately.
#
# The budget is much larger than the 300s the other engines use, and for a
# reason that is structural rather than incidental: booting this image is not
# "start a server", it is "start six JVMs, then run one indexing task per table,
# each of which forks a peon JVM, writes a segment, publishes it, and waits for
# the historical to load it". On an unloaded machine world takes ~50s and the
# widest dataset (usda, ten tables) a few minutes; on a loaded or emulated CI
# runner that multiplies. 900s leaves room for the worst of those without ever
# being the thing that fails first -- the entrypoint's own per-phase timeouts
# and its "a service exited" check both fire earlier and with a real diagnosis.
READY_TIMEOUT="${READY_TIMEOUT:-900}"
deadline=$(( SECONDS + READY_TIMEOUT ))
if ! wait_for_log_marker "druid-dataset: ${DATASETS[0]} ready" "$deadline"; then
  fail "${IMAGE}: Druid did not become ready in time (${READY_TIMEOUT}s)"
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
