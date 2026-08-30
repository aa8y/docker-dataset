# lib.sh -- shared plumbing for the run*.sh integration-test scripts in this
# directory. Not an entry point: source it, don't run it.
#
# Each engine script sources this (via its own SCRIPT_DIR) after defining:
#
#   UPDATE                   0/1, whether --update was passed
#   TAG, DATASETS_CSV        the parsed positional arguments
#   DATASETS                 DATASETS_CSV split into an array
#   IMAGE                    the image under test (<repository>:<tag>)
#   VOLATILE_DATASETS        engine's datasets with drifting counts (is_volatile)
#   VOLATILE_TAG_PREFIXES    tag prefixes whose datasets are all volatile
#   SCRIPT_DIR               this directory (also how the script found lib.sh)
#   EXPECTED_SUBDIR          subdir of test/expected/ holding the engine's
#                            files ("" for postgres, the original engine)
#
# The server engines additionally set CONTAINER (next to their cleanup trap)
# before calling wait_for_log_marker. Everything here is bash 3.2 compatible.

# All human-readable logging goes to stderr, which keeps stdout free for
# machine-readable output (`dave test` streams both live). Diagnostics staying
# on stderr is also what keeps CI failures -- which tables/counts mismatched --
# legible when stdout is being piped or captured.
# Exit-code contract, shared by every run*.sh and relied on by with-retry.sh:
#
#   0            everything asserted clean.
#   $ASSERT_RC   a deterministic, real failure: a count/table mismatch, or an
#                expected file that isn't there. The image and the expectations
#                are both fixed inputs, so a second run produces the identical
#                verdict -- retrying only doubles the CI bill and delays the
#                red. Never retried.
#   anything     potentially transient infra trouble: a readiness timeout, a
#   else         docker or network error, `set -e` fallout from an unexpected
#                command failure. May be retried.
#
# 3 rather than 2, which shells conventionally use for usage errors, and well
# clear of the 126/127/128+n range the shell assigns itself.
ASSERT_RC=3

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; RESET=$'\033[0m'
info() { printf '%s\n' "$*" >&2; }
pass() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
fail() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; }

# Where this engine's expected files live on disk, and how log lines refer to
# them (their path relative to test/).
EXPECTED_LABEL="expected${EXPECTED_SUBDIR:+/${EXPECTED_SUBDIR}}"
EXPECTED_DIR="${SCRIPT_DIR}/../${EXPECTED_LABEL}"

is_volatile() {
  # is_volatile <db> — true if this dataset's counts drift between builds,
  # either because the dataset is explicitly listed in VOLATILE_DATASETS or
  # because $TAG matches a VOLATILE_TAG_PREFIXES entry (each image carries a
  # single dataset, so the tag decides).
  local db="$1"
  case " ${VOLATILE_DATASETS:-} " in *" $db "*) return 0 ;; esac
  local prefix
  for prefix in ${VOLATILE_TAG_PREFIXES:-}; do
    case "$TAG" in "$prefix"*) return 0 ;; esac
  done
  return 1
}

sql_squote() {
  # sql_squote <s> — <s> with every embedded single quote doubled: the SQL
  # string-literal escaping shared by sqlite, MariaDB and CockroachDB. Kept as
  # a helper because the tempting inline form `${s//\'/\'\'}` is a trap: inside
  # double quotes bash only treats backslash specially before $ ` " \ and
  # newline, so the replacement text keeps its backslashes and writes them
  # into the SQL.
  local sq=\'
  printf '%s' "${1//$sq/$sq$sq}"
}

counts_to_json() {
  # counts_to_json <sep> — fold `<key><sep><count>` rows on stdin into a JSON
  # object {"<key>": <count>, ...}. <sep> is the SQL client's column separator:
  # sqlite3's list mode emits `|`, `mariadb -B` and `cockroach --format=tsv`
  # emit tabs.
  local sep="$1"
  jq -R -s --arg sep "$sep" \
    'split("\n") | map(select(length>0) | split($sep)) | map({(.[0]): (.[1]|tonumber)}) | add // {}'
}

write_expected() {
  # write_expected <db> <actual-json> — (re)generate the expected file for <db>
  # from freshly measured counts (the --update path). Volatile datasets get a
  # ">=<count>" floor per table instead of an exact number, so counts that
  # drift upstream between builds don't fail later assert runs. The floor is
  # set at 95% of the measured count, not the exact value: volatile upstreams
  # are not monotonic (omdb merges records away, GeoNames cities drop below
  # the population threshold), and an exact-count floor breaks on the first
  # small shrink. 5% slack still catches real load failures.
  local db="$1" actual="$2"
  mkdir -p "$EXPECTED_DIR"
  if is_volatile "$db"; then
    printf '%s\n' "$actual" | jq -S 'map_values(">=" + (. * 0.95 | floor | tostring))' > "${EXPECTED_DIR}/${db}.json"
  else
    printf '%s\n' "$actual" | jq -S . > "${EXPECTED_DIR}/${db}.json"
  fi
  pass "${db}: wrote $(jq 'length' <<<"$actual") tables to ${EXPECTED_LABEL}/${db}.json"
}

check_counts() {
  # check_counts <db> <expected-json> <actual-json> — compare measured counts
  # against the expectations, reporting every discrepancy as a red line.
  # Returns 0 when everything matches, 1 otherwise.
  #
  # Callers invoke this as `check_counts ... || rc=1`, and in that context bash
  # ignores `set -e` for the entire function body — so each jq is checked
  # explicitly, keeping the historical hard abort (with jq's own diagnostic on
  # stderr) if one fails outright, e.g. on an expected file that isn't valid
  # JSON. A bare `exit` propagates the failed jq's exit status.
  local db="$1" expected="$2" actual="$3"
  local missing extra mismatch db_ok t m

  # Table-set diff: keys present in one side but not the other.
  missing="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($e|keys_unsorted) - ($a|keys_unsorted) | .[]')" || exit
  extra="$(jq -rn --argjson e "$expected" --argjson a "$actual" \
    '($a|keys_unsorted) - ($e|keys_unsorted) | .[]')" || exit
  # Count check on tables present in both: a number means exact match, a
  # ">=N" / ">N" string means a floor. Anything else must land in the
  # "invalid expected spec" branch, which takes both halves of the guard
  # around capture: on a non-matching *string* capture yields an empty stream
  # (not null!), and binding empty to $m would silently erase the whole
  # expression for that key -- `// null` turns empty back into null; on a
  # non-string (null, bool, ...) capture errors outright, which under
  # `set -euo pipefail` used to abort the whole script with an opaque jq
  # message -- `try ... catch null` turns the error into null.
  mismatch="$(jq -rn --argjson e "$expected" --argjson a "$actual" '
    ($e|keys_unsorted) as $ek
    | ($ek - ($ek - ($a|keys_unsorted)))[] as $k
    | $e[$k] as $ev | $a[$k] as $av
    | if ($ev|type) == "number" then
        (if $av != $ev then "\($k): expected \($ev) got \($av)" else empty end)
      else
        (($ev | try capture("^(?<op>>=|>)(?<n>[0-9]+)$") catch null) // null) as $m
        | if $m == null then "\($k): invalid expected spec \"\($ev)\""
          else ($m.n | tonumber) as $n
            | if   ($m.op == ">"  and $av >  $n) then empty
              elif ($m.op == ">=" and $av >= $n) then empty
              else "\($k): expected \($ev) got \($av)" end
          end
      end')" || exit

  # A database that yields no tables at all while some were expected is not a
  # per-table problem -- the database itself is absent (a typo'd name yields
  # zero information_schema rows, not an error). One clear line beats a wall of
  # per-table "missing table" lines.
  if [[ -n "$missing" && "$(jq 'length' <<<"$actual")" -eq 0 ]]; then
    fail "${db}: no tables found — wrong database name?"
    return 1
  fi

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
    return 0
  fi
  return 1
}

wait_for_log_marker() {
  # wait_for_log_marker <marker> <deadline> — <deadline> is an absolute $SECONDS
  # value. A single `docker logs -f` stream fed to `grep -q -m1`, rather than
  # re-grepping the whole log once a second (which re-reads every byte written so
  # far on every poll, so the cost of waiting grows with the log). The follow
  # replays the log from the start, so a marker printed before we began watching
  # is still seen; grep exits at the first match; and the stream ends by itself
  # if the container dies, which turns a crashed container into an immediate
  # failure instead of a full-budget wait. The loop below therefore only has to
  # enforce the wall-clock deadline.
  #
  # grep reads from a process substitution rather than a pipeline on purpose:
  # bash waits for *every* member of a pipeline, and `docker logs -f` only
  # notices the closed pipe when it next writes, so a server that goes quiet
  # right after printing the marker would keep the watcher alive -- and the
  # match unreported -- until the deadline. A finished or killed watcher may
  # leave a lingering `docker logs -f`; the EXIT trap's `docker rm -f` reaps it
  # along with the container.
  local marker="$1" deadline="$2" watcher
  ( grep -q -m1 -- "$marker" < <(docker logs -f "$CONTAINER" 2>&1) ) & watcher=$!
  while kill -0 "$watcher" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
      return 1
    fi
    sleep 1
  done
  wait "$watcher"
}

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
# --update neither reads nor writes one, and DDS_DEDUPE=0 opts out entirely.
#
# Correctness here does not depend on the cache being ephemeral. The key is the
# image ID, and the stamp body is the dataset list plus the exact bytes of every
# expected file the run reads: change the image and the key moves, change an
# expectation and the body no longer matches, either way the entry misses and
# the run happens. That is what makes it safe for CI to persist this directory
# across re-run attempts of the same commit -- a re-run then skips the tags that
# already passed, which is the whole point, without ever being able to skip a
# tag whose image or expectations differ from the ones that passed.
CACHE_DIR="${DDS_TEST_CACHE:-${TMPDIR:-/tmp}/docker-dataset-itest}"
stamp_file=""

stamp_contents() {
  local db
  printf '%s\n' "$DATASETS_CSV"
  for db in "${DATASETS[@]}"; do
    cat "${EXPECTED_DIR}/${db}.json" 2>/dev/null || true
  done
}

dedupe_skip() {
  # dedupe_skip — true when this image ID has already passed with exactly the
  # current expectations, so the whole run can be skipped. As a side effect,
  # resolves and remembers $stamp_file when the image exists locally, arming
  # record_pass_stamp. An image we cannot resolve locally is simply not
  # deduped; `docker run` will pull it as before.
  local image_id short_id
  [[ "$UPDATE" -eq 0 && "${DDS_DEDUPE:-1}" != "0" ]] || return 1
  image_id="$(docker image inspect -f '{{.Id}}' "$IMAGE" 2>/dev/null || true)"
  [[ -n "$image_id" ]] || return 1
  mkdir -p "$CACHE_DIR"
  stamp_file="${CACHE_DIR}/${image_id//[^a-zA-Z0-9]/-}"
  if [[ -f "$stamp_file" ]] && stamp_contents | cmp -s - "$stamp_file"; then
    short_id="${image_id#sha256:}"
    pass "${IMAGE}: identical image (${short_id:0:12}) already passed as an earlier tag; skipping"
    return 0
  fi
  return 1
}

record_pass_stamp() {
  # record_pass_stamp <rc> — after a clean assert run, record the pass so a
  # later tag resolving to this same image ID with these same expectations can
  # skip the run entirely. Clean runs only ($stamp_file is empty in --update
  # mode and when dedupe is off).
  local rc="$1"
  if [[ "$rc" -eq 0 && -n "$stamp_file" ]]; then
    stamp_contents > "$stamp_file"
  fi
}
