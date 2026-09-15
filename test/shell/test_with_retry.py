"""TST-03 (retry-knob validation) plus the core retry-classification contract of
test/integration/with-retry.sh, which had no automated coverage (TST-08).

with-retry.sh resolves its target relative to its own directory, so each test
copies the wrapper into a temp dir beside a fake ``probe.sh`` whose exit code and
per-attempt logging the test controls.
"""
import shutil

import pytest
from shellkit import ROOT, fake_bin, run, requires_shell

pytestmark = requires_shell

PROBE = r'''
echo attempt >> "$ATTEMPT_LOG"
exit "${PROBE_RC:-0}"
'''


def _stage(tmp_path):
    d = tmp_path / "itest"
    d.mkdir()
    shutil.copy(ROOT / "test/integration/with-retry.sh", d / "with-retry.sh")
    fake_bin(d, "probe.sh", PROBE)
    return d


def _run(tmp_path, env, retries=None, delay=None):
    d = _stage(tmp_path)
    log = tmp_path / "attempts.log"
    e = {"ATTEMPT_LOG": str(log)}
    if retries is not None:
        e["DDS_ITEST_RETRIES"] = retries
    if delay is not None:
        e["DDS_ITEST_RETRY_DELAY"] = delay
    e.update(env)
    r = run(d / "with-retry.sh", args=["probe.sh"], env=e)
    attempts = log.read_text().count("attempt") if log.exists() else 0
    return r, attempts


def test_pass_runs_once(tmp_path):
    r, n = _run(tmp_path, {"PROBE_RC": "0"})
    assert r.returncode == 0
    assert n == 1


def test_assert_rc_never_retried(tmp_path):
    r, n = _run(tmp_path, {"PROBE_RC": "3"}, retries="2", delay="0")
    assert r.returncode == 3
    assert n == 1


def test_transient_retried_to_budget(tmp_path):
    r, n = _run(tmp_path, {"PROBE_RC": "1"}, retries="2", delay="0")
    assert r.returncode == 1
    assert n == 3            # first attempt + 2 retries


def test_zero_retries_disables(tmp_path):
    r, n = _run(tmp_path, {"PROBE_RC": "1"}, retries="0", delay="0")
    assert r.returncode == 1
    assert n == 1


@pytest.mark.parametrize("bad", ["banana", "-1", "1.5"])
def test_bad_retries_rejected_before_running(tmp_path, bad):
    r, n = _run(tmp_path, {"PROBE_RC": "0"}, retries=bad, delay="0")
    assert r.returncode == 2, r.stderr
    assert n == 0            # probe never ran
    assert "DDS_ITEST_RETRIES" in r.stderr


@pytest.mark.parametrize("bad", ["banana", "-5", "2s"])
def test_bad_delay_rejected_before_running(tmp_path, bad):
    r, n = _run(tmp_path, {"PROBE_RC": "0"}, retries="1", delay=bad)
    assert r.returncode == 2, r.stderr
    assert n == 0
    assert "DDS_ITEST_RETRY_DELAY" in r.stderr


def test_empty_knob_falls_back_to_default(tmp_path):
    # An empty (vs unset) env var is `${VAR:-default}` territory: treated as the
    # default, not as invalid input, so a transient failure still retries once.
    r, n = _run(tmp_path, {"PROBE_RC": "1", "DDS_ITEST_RETRY_DELAY": "0"}, retries="")
    assert r.returncode == 1, r.stderr
    assert n == 2            # default of 1 retry -> two attempts
