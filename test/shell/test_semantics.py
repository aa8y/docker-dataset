"""TST-07: lib.sh's check_semantics runs optional value-level probes (a queried
value must equal an expected string), catching content regressions that row
counts miss -- and is a strict no-op when a dataset ships no checks file or the
engine defines no probe_query.

Exercised through a harness that sources lib.sh, defines a controllable
probe_query, and points EXPECTED_DIR at a temp directory holding the checks file.
No Docker or database is involved; probe_query's output and exit code are driven
by the environment.
"""
import json
import shutil

from shellkit import ROOT, run, requires_shell

pytestmark = requires_shell

HARNESS_HEAD = r'''
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATASETS_CSV="foo"; DATASETS=(foo)
. "${SCRIPT_DIR}/lib.sh"
# lib.sh derives EXPECTED_DIR from SCRIPT_DIR on source, so override it here,
# after, to point at the temp checks directory this test staged.
EXPECTED_DIR="$SCRIPT_DIR/exp"
'''

PROBE_FN = 'probe_query() { [ -z "${PROBE_FAIL:-}" ] || return 1; printf "%s\\n" "${PROBE_OUT:-}"; }\n'
CALL = 'check_semantics foo\n'


def _stage(tmp_path, checks=None, with_probe=True):
    d = tmp_path / "integration"
    d.mkdir()
    for f in ("lib.sh", "with-retry.sh"):
        shutil.copy(ROOT / "test/integration" / f, d / f)
    exp = d / "exp"
    exp.mkdir()
    if checks is not None:
        (exp / "foo.checks.json").write_text(json.dumps(checks))
    body = HARNESS_HEAD + (PROBE_FN if with_probe else "") + CALL
    harness = d / "harness.sh"
    harness.write_text("#!/usr/bin/env bash\n" + body)
    return harness


def _run(harness, env=None):
    return run(harness, env=env or {})


def test_no_checks_file_is_noop(tmp_path):
    h = _stage(tmp_path, checks=None)
    r = _run(h)
    assert r.returncode == 0, r.stderr
    assert "semantic check" not in r.stderr


def test_no_probe_query_defined_is_noop(tmp_path):
    h = _stage(tmp_path, checks=[{"name": "x", "sql": "SELECT 1", "expect": "1"}],
               with_probe=False)
    r = _run(h)
    assert r.returncode == 0, r.stderr
    assert "semantic check" not in r.stderr


def test_passing_probe(tmp_path):
    h = _stage(tmp_path, checks=[{"name": "no_null_codes", "sql": "Q", "expect": "0"}])
    r = _run(h, {"PROBE_OUT": "0"})
    assert r.returncode == 0, r.stderr
    assert "1 semantic check(s) passed" in r.stderr


def test_failing_probe(tmp_path):
    h = _stage(tmp_path, checks=[{"name": "no_null_codes", "sql": "Q", "expect": "0"}])
    r = _run(h, {"PROBE_OUT": "7"})
    assert r.returncode == 1, r.stderr
    assert "no_null_codes" in r.stderr
    assert "expected [0] got [7]" in r.stderr


def test_query_error_fails(tmp_path):
    h = _stage(tmp_path, checks=[{"name": "probe", "sql": "Q", "expect": "0"}])
    r = _run(h, {"PROBE_FAIL": "1"})
    assert r.returncode == 1, r.stderr
    assert "query failed" in r.stderr


def test_trailing_whitespace_trimmed(tmp_path):
    # probe_query appends a newline; a trailing-space value must still match.
    h = _stage(tmp_path, checks=[{"name": "probe", "sql": "Q", "expect": "42"}])
    r = _run(h, {"PROBE_OUT": "42   "})
    assert r.returncode == 0, r.stderr


def test_multiple_probes_all_run(tmp_path):
    h = _stage(tmp_path, checks=[
        {"name": "a", "sql": "Q", "expect": "5"},
        {"name": "b", "sql": "Q", "expect": "5"},
    ])
    r = _run(h, {"PROBE_OUT": "5"})
    assert r.returncode == 0, r.stderr
    assert "2 semantic check(s) passed" in r.stderr
