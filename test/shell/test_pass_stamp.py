"""TST-04: an integration pass stamp must encode the identity of the test
protocol, not only the image ID and expected bytes, so a stamp written by one
version of the assertion code cannot skip a corrected assertion.

lib.sh's stamp_contents is exercised through a tiny harness that sets the few
variables a runner would define before sourcing it, then prints the stamp body.
Changing any protocol file (lib.sh, with-retry.sh, the runner) must change the
``protocol`` line.
"""
import shutil

from shellkit import ROOT, run, requires_shell

pytestmark = requires_shell

HARNESS = r'''
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATASETS_CSV="foo"; DATASETS=(foo); EXPECTED_DIR="$SCRIPT_DIR/exp"
. "${SCRIPT_DIR}/lib.sh"
stamp_contents
'''


def _stage(tmp_path):
    d = tmp_path / "integration"
    d.mkdir()
    for f in ("lib.sh", "with-retry.sh"):
        shutil.copy(ROOT / "test/integration" / f, d / f)
    # The harness itself plays the "runner" role: lib.sh captures DDS_RUNNER as
    # its sourcer at source time, so protocol_id folds this file in too.
    harness = d / "harness.sh"
    harness.write_text("#!/usr/bin/env bash\n" + HARNESS)
    return d, harness


def _protocol_line(harness):
    r = run(harness)
    assert r.returncode == 0, r.stderr
    first = r.stdout.splitlines()[0]
    assert first.startswith("protocol "), r.stdout
    return first


def test_stamp_carries_protocol_digest(tmp_path):
    _d, harness = _stage(tmp_path)
    line = _protocol_line(harness)
    # 64-hex sha256 after the label
    assert len(line.split()[1]) == 64


def test_editing_lib_changes_protocol(tmp_path):
    d, harness = _stage(tmp_path)
    before = _protocol_line(harness)
    with (d / "lib.sh").open("a") as fh:
        fh.write("\n# harmless trailing comment\n")
    assert _protocol_line(harness) != before


def test_editing_wrapper_changes_protocol(tmp_path):
    d, harness = _stage(tmp_path)
    before = _protocol_line(harness)
    with (d / "with-retry.sh").open("a") as fh:
        fh.write("\n# harmless trailing comment\n")
    assert _protocol_line(harness) != before
