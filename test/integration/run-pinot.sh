#!/usr/bin/env bash
#
# Live integration / smoke test for an aa8y/pinot-dataset image.
#
# The Apache Pinot counterpart of run-cockroach.sh / run-mysql.sh. Boots the
# image, waits for the entrypoint's ready marker (which is printed only after
# every table has reached its build-time row count), then for each dataset
# shipped in the image asserts that:
#   1. the set of tables present exactly matches the expected set
#      (no missing tables, no unexpected extras), and
#   2. SELECT count(*) on every table matches the expected row count.
#
# Expected tables and counts are stored per-dataset as JSON under
# test/expected/pinot/<dataset>.json, e.g.
#
#     { "world.city": 4079, "world.country": 239, ... }
#
# keyed by <dataset>.<table>. Pinot has no schemas or databases -- a cluster is
# a flat namespace of tables -- and each image carries exactly one dataset, so
# the dataset name is a prefix this script adds rather than anything the engine
# reports. Counts are authoritative count(*). A value can be either:
#   - a number  -> assert count(*) == N exactly (deterministic datasets), or
#   - ">=N"     -> assert count(*) >= N (a floor), used for datasets whose data
#                  is fetched from a live upstream at build time and so drifts
#                  between builds.
#
# Both the table list and the counts are read over Pinot's REST APIs from
# *inside* the container (the official image ships curl), which keeps this
# script free of published ports and so safe to run several at a time.
#
# Usage:
#   run-pinot.sh <tag> <datasets-csv>            # assert against expected/*.json
#   run-pinot.sh --update <tag> <datasets-csv>   # (re)generate expected/*.json
set -euo pipefail

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
  UPDATE=1
  shift
fi

TAG="${1:?usage: run-pinot.sh [--update] <tag> <datasets-csv>}"
DATASETS_CSV="${2:?usage: run-pinot.sh [--update] <tag> <datasets-csv>}"
IFS=',' read -ra DATASETS <<< "$DATASETS_CSV"

REPOSITORY="${REPOSITORY:-aa8y/pinot-dataset}"
IMAGE="${REPOSITORY}:${TAG}"

# Datasets whose row data is fetched from a live upstream at build time, so
# exact counts drift between builds. For these, --update records a floor
# (">=<count-at-build-time>") instead of an exact count. Same knobs as the other
# run scripts; Pinot ships no StackExchange tags, so unlike its siblings there
# is no volatile tag *prefix* to match -- the variable is set empty rather than
# left undefined so the intent is on the record.
VOLATILE_DATASETS="moma geonames openflights"
VOLATILE_TAG_PREFIXES=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_SUBDIR="pinot"
. "${SCRIPT_DIR}/lib.sh"

CONTAINER="pinot-ds-test-${TAG//[^a-zA-Z0-9_.-]/-}-$$"

# `-v` as well as `-f`, which the other engines' scripts do not need: the
# official Pinot image declares /opt/pinot/configs and /opt/pinot/data as
# VOLUMEs, so every `docker run` of it creates two anonymous volumes that
# outlive the container. (None of the other engines' bases declare any.) The
# images deliberately keep their runtime state elsewhere -- /var/lib/pinot, see
# pinot/conf/*.conf -- so those volumes are always empty, but at eight
# containers per shard per CI run they would still accumulate indefinitely on a
# long-lived runner or a developer's machine. `-v` removes anonymous volumes
# only; a named volume someone attached deliberately is left alone.
cleanup() { docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Identical-image dedupe: some tags are just a second name for the same build
# (`latest` = `world`), and what a container does is a pure function of its
# image, so a clean pass need not be re-proven. See lib.sh for the stamp
# semantics.
if dedupe_skip; then exit 0; fi

pinot_tables() {
  # pinot_tables — the cluster's table names, one per line. The controller's
  # /tables returns {"tables":[...]} with the bare names (no _OFFLINE suffix),
  # which is exactly the namespace the expected files are keyed on.
  docker exec "$CONTAINER" curl -sS -m 30 http://localhost:9000/tables 2>/dev/null \
    | jq -r '.tables[]?' | sort
}

# Authoritative counts for every table, as a JSON object keyed by
# <dataset>.<table>. One `docker exec` for the whole dataset, not one per table:
# an exec costs a container round-trip, and usda ships ten tables. Pinot's v1
# query engine has no UNION ALL, so the counts genuinely are one query each --
# they are just all issued from a single shell inside the container.
actual_counts() {
  local db="$1" t
  local table_arr=()
  while IFS= read -r t; do
    [[ -n "$t" ]] && table_arr+=("$t")
  done <<<"$(pinot_tables)"
  # Counted rather than testing the raw output for emptiness: under `set -u`,
  # expanding an empty array is an error in bash 3.2, so the guard has to be on
  # the array itself. No tables at all means the cluster answered but carries
  # nothing, which check_counts reports as one clear "no tables found" line.
  if [[ "${#table_arr[@]}" -eq 0 ]]; then printf '{}\n'; return; fi

  # The inner script is quoted-heredoc'd so the host shell expands none of it;
  # the dataset name and table list arrive as positional arguments instead.
  # Pinot returns query errors *inside* a 200 response, in "exceptions", so a
  # non-empty exceptions array is treated as a hard failure rather than parsed
  # for a count -- a broker that answers "0 rows" for a table whose segments
  # have not landed must not be mistaken for an empty table.
  docker exec -i "$CONTAINER" bash -s "$db" "${table_arr[@]}" <<'INNER' | counts_to_json ','
db="$1"; shift
for t in "$@"; do
  resp="$(curl -sS -m 60 -X POST -H 'Content-Type: application/json' \
    -d "{\"sql\":\"SELECT COUNT(*) FROM \\\"${t}\\\"\"}" \
    http://localhost:8099/query/sql)" || exit 1
  case "$resp" in
    *'"exceptions":[]'*) ;;
    *) printf 'query error on %s: %s\n' "$t" "$resp" >&2; exit 1 ;;
  esac
  n="${resp#*'"rows":[['}"
  n="${n%%]]*}"
  case "$n" in
    ''|*[!0-9]*) printf 'unparseable count for %s: %s\n' "$t" "$resp" >&2; exit 1 ;;
  esac
  printf '%s.%s,%s\n' "$db" "$t" "$n"
done
INNER
}

info "==> ${IMAGE}"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

# Wait for the entrypoint's ready marker. Unlike the other server engines there
# is no second "and now can the client connect?" phase: the marker is printed
# only after the entrypoint has created every table, ingested every CSV, *and*
# polled the broker until each table reports the exact row count recorded at
# build time. So by the time it appears the cluster is not merely up, it is
# fully loaded -- there is no window in which a half-ingested dataset could be
# measured.
#
# The budget is larger than the 300s the other engines use, for two reasons
# that are both structural rather than incidental: this container starts two
# JVMs (ZooKeeper, then controller+broker+server) and waits for Helix to settle,
# which is ~40s before any data moves; and each table's rows are turned into a
# real Pinot segment at start rather than inserted, which on the widest datasets
# (usda, dellstore) is minutes of CPU. 600s leaves room for both on a loaded or
# emulated runner without being so generous that a genuinely wedged container
# ties up a shard.
READY_TIMEOUT="${READY_TIMEOUT:-600}"
deadline=$(( SECONDS + READY_TIMEOUT ))
if ! wait_for_log_marker "pinot-dataset: ${DATASETS[0]} ready" "$deadline"; then
  fail "${IMAGE}: Pinot did not become ready in time (${READY_TIMEOUT}s)"
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
