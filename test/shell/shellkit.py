"""Helpers for the shell-utility regression tests (``test/shell``).

The repository's Bash utilities -- the integration-test wrapper and runners, the
``dataset-checksum`` cache, and ``merge-manifests`` -- carried no automated
tests before this suite (audit 2026-09-14, TST-08). These exercise them with
fake ``docker`` / ``curl`` / ``git`` executables placed on ``PATH``, so they
need no Docker daemon, no network, and no built image, and run in CI beside the
Python transform unit tests. ``bash`` and ``jq`` must be present -- they already
are on the CI runners and for anyone running the integration tests -- and the
suite skips itself if either is missing.

The pattern in every test: build a temp directory of fake commands with
``fake_bin`` (each a tiny shell script whose behavior a test drives through the
environment), then ``run`` the target script with that directory prepended to
``PATH``.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# One skip mark the test modules share, evaluated once at import.
_MISSING = [t for t in ("bash", "jq") if shutil.which(t) is None]
requires_shell = pytest.mark.skipif(
    bool(_MISSING),
    reason="shell tests need %s on PATH" % ", ".join(_MISSING),
)


def fake_bin(dirpath, name, body):
    """Create an executable shim ``name`` in ``dirpath`` from shell ``body``.

    A ``#!/usr/bin/env bash`` shebang is prepended when ``body`` has none.
    Returns the path written.
    """
    path = Path(dirpath) / name
    if not body.startswith("#!"):
        body = "#!/usr/bin/env bash\n" + body
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run(script, args=(), env=None, path_prepend=None, cwd=None, stdin=None):
    """Run a Bash ``script`` and capture its result.

    ``script`` is a path: absolute, or relative to the repository root. Extra
    ``env`` overrides the inherited environment; ``path_prepend`` (a directory
    of fake commands) is prepended to ``PATH``; ``cwd`` defaults to the repo
    root. Returns the ``subprocess.CompletedProcess`` (text mode).
    """
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    full_env = os.environ.copy()
    if path_prepend is not None:
        full_env["PATH"] = "%s%s%s" % (path_prepend, os.pathsep, full_env["PATH"])
    if env:
        full_env.update({k: str(v) for k, v in env.items()})
    return subprocess.run(
        ["bash", str(script_path), *[str(a) for a in args]],
        env=full_env,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        input=stdin,
    )
