"""TST-01: run-sqlite.sh must not misfile an infrastructure failure of the
integrity check as deterministic database corruption.

``integrity_ok`` runs ``PRAGMA quick_check`` via ``docker run``. Before the fix a
Docker/daemon failure (empty output) was indistinguishable from a corrupt
database: both returned 1 and the caller stamped ``$ASSERT_RC`` (3), which
with-retry.sh never retries -- so a transient daemon blip permanently failed the
shard. The fix classifies a docker-level failure (exit >=125) as retryable (2)
while a database that opened and reported damage stays deterministic (3).
"""
from shellkit import fake_bin, run, requires_shell

pytestmark = requires_shell

SCRIPT = "test/integration/run-sqlite.sh"

# A fake ``docker`` covering only what run-sqlite.sh invokes: ``docker run ...
# sqlite3 ... <sql>``. The last argument is the SQL; the quick_check output and
# its exit code are driven by the environment so each test picks a scenario.
FAKE_DOCKER = r'''
cmd="$1"; shift || true
if [ "$cmd" != "run" ]; then exit 0; fi
sql="${@: -1}"
case "$sql" in
  *quick_check*)
    rc="${FAKE_QC_RC:-0}"
    if [ "$rc" -eq 0 ]; then printf '%s\n' "${FAKE_QC_OUT:-ok}"; fi
    exit "$rc" ;;
  *sqlite_master*)
    printf '%s' "${FAKE_TABLES:-}"; exit 0 ;;
  *)
    printf '%s' "${FAKE_COUNTS:-}"; exit 0 ;;
esac
'''


def _run(tmp_path, env):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_bin(bin_dir, "docker", FAKE_DOCKER)
    base = {"DDS_DEDUPE": "0"}   # skip the image-inspect dedupe path entirely
    base.update(env)
    return run(SCRIPT, args=["chinook_probe", "chinook_probe"],
               env=base, path_prepend=bin_dir)


def test_docker_failure_is_retryable_not_assert_rc(tmp_path):
    # quick_check cannot even run (daemon down / socket denied -> exit 125).
    r = _run(tmp_path, {"FAKE_QC_RC": "125"})
    assert r.returncode == 2, r.stderr        # retryable, NOT the deterministic 3
    assert "transient" in r.stderr


def test_real_corruption_is_assert_rc(tmp_path):
    # quick_check ran and found damage in an openable file.
    r = _run(tmp_path, {"FAKE_QC_RC": "0",
                        "FAKE_QC_OUT": "*** in database main ***\nrow 1 missing from index ix"})
    assert r.returncode == 3, r.stderr        # $ASSERT_RC, never retried
    assert "quick_check failed" in r.stderr


def test_healthy_db_proceeds_past_integrity(tmp_path):
    # quick_check "ok" -> integrity passes; with no expected file for this db the
    # run still fails deterministically, but with the missing-file message, which
    # proves the ok path was taken rather than the corruption branch.
    r = _run(tmp_path, {"FAKE_QC_RC": "0", "FAKE_QC_OUT": "ok", "FAKE_TABLES": "Album\n"})
    assert r.returncode == 3, r.stderr
    assert "missing expected file" in r.stderr
    assert "quick_check failed" not in r.stderr
