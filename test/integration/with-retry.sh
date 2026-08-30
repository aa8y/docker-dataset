#!/usr/bin/env bash
#
# Retry wrapper for the run*.sh integration-test scripts.
#
# These tests boot real containers and pull real images, so a slice of their
# failures say nothing about the images under test: a readiness budget blown by
# a loaded or emulated runner, a registry hiccup, a `docker exec` that lost its
# daemon. Re-running those costs one container boot and usually turns the shard
# green; re-running the *other* kind costs the same boot and is guaranteed to
# reach the identical verdict, because a run*.sh assertion is a pure function of
# the image ID and the bytes of the expected files -- neither of which a second
# attempt changes. So the scripts separate the two by exit code (the contract
# lives in lib.sh):
#
#   0            pass                        -> return immediately
#   $ASSERT_RC   deterministic real failure  -> return immediately, never retry
#   anything     possibly-transient trouble  -> retry
#   else
#
# Exempting the assertion code is the point of the wrapper. Retrying a genuine
# count mismatch hides nothing (it fails again) but doubles the time to red and
# the CI bill for every real regression, which is exactly when the feedback loop
# matters most.
#
# Usage:  with-retry.sh <script-basename> <args...>
#   e.g.  REPOSITORY=aa8y/postgres-dataset with-retry.sh run.sh iso3166 iso3166
#
# Knobs:
#   DDS_ITEST_RETRIES      extra attempts after the first (default 1, so two
#                          attempts in total). 0 disables retrying entirely.
#   DDS_ITEST_RETRY_DELAY  seconds to wait between attempts (default 10), long
#                          enough for a momentary daemon or registry blip to
#                          clear, short enough not to dominate a shard.
#
# bash 3.2 compatible (macOS), like the scripts it wraps.
set -euo pipefail

# Must match lib.sh's ASSERT_RC. Not sourced from there: lib.sh is written to be
# sourced *after* a run script has defined TAG, DATASETS and friends, and this
# wrapper has none of them.
ASSERT_RC=3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

script="${1:?usage: with-retry.sh <script-basename> <args...>}"
shift

# Resolved against this file's own directory, not the caller's cwd: `dave test`
# runs these from the repo root, but the wrapper should be callable from
# anywhere and can only be sure of where it itself lives.
target="${SCRIPT_DIR}/${script}"
if [[ ! -f "$target" ]]; then
  printf 'with-retry.sh: no such script: %s\n' "$target" >&2
  exit 2
fi

retries="${DDS_ITEST_RETRIES:-1}"
delay="${DDS_ITEST_RETRY_DELAY:-10}"

attempt=0
while :; do
  rc=0
  # `|| rc=$?` rather than a bare call: under `set -e` a failing child would
  # otherwise take the wrapper down with it before we could classify the code.
  bash "$target" "$@" || rc=$?

  if [[ "$rc" -eq 0 || "$rc" -eq "$ASSERT_RC" ]]; then
    exit "$rc"
  fi

  # Out of budget: report the last attempt's code as our own, so the caller sees
  # the real failure rather than a wrapper-invented one.
  if [[ "$attempt" -ge "$retries" ]]; then
    exit "$rc"
  fi

  attempt=$(( attempt + 1 ))
  # `${*:+ $*}` so an argument-less invocation doesn't log a stray double space.
  printf 'with-retry.sh: %s failed with code %s (possibly transient); retrying in %ss [attempt %s/%s]\n' \
    "${script}${*:+ $*}" "$rc" "$delay" "$attempt" "$retries" >&2
  sleep "$delay"
done
