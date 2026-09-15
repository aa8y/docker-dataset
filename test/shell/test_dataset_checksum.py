"""TST-02: bin/dataset-checksum must accept a cache/fallback entry only when it
is a real 16-hex fingerprint, plus coverage for the memo/fallback machinery that
had none (TST-08).

A fake ``curl`` drives the "clean" vs "degraded" upstream-metadata paths; only
plain https URLs are used, so the archive.org and git branches never run.
"""
import hashlib
import re

from shellkit import fake_bin, run, requires_shell

pytestmark = requires_shell

SCRIPT = "bin/dataset-checksum"
HEX16 = re.compile(r'^[0-9a-f]{16}$')
URL = "https://inert.invalid/data.csv"

# clean: emit a header http_meta greps; degraded: fail like a dead upstream.
FAKE_CURL = r'''
if [ "${FAKE_CURL_MODE:-fail}" = "fail" ]; then exit 22; fi
printf 'HTTP/1.1 200 OK\r\nETag: "deadbeef"\r\nContent-Length: 123\r\n\r\n'
exit 0
'''


def _key(url=URL):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _dirs(tmp_path):
    cache = tmp_path / "cache"; cache.mkdir()
    fb = tmp_path / "fb"; fb.mkdir()
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    fake_bin(bin_dir, "curl", FAKE_CURL)
    return cache, fb, bin_dir


def test_valid_memo_entry_is_a_hit(tmp_path):
    cache, _fb, bin_dir = _dirs(tmp_path)
    (cache / _key()).write_text("0123456789abcdef\n")
    r = run(SCRIPT, args=[URL], env={"DATASET_CHECKSUM_CACHE": str(cache)},
            path_prepend=bin_dir)
    assert r.returncode == 0
    assert r.stdout.strip() == "0123456789abcdef"


def test_garbage_memo_entry_is_a_miss(tmp_path):
    cache, _fb, bin_dir = _dirs(tmp_path)
    (cache / _key()).write_text("garbage\n")
    r = run(SCRIPT, args=[URL],
            env={"DATASET_CHECKSUM_CACHE": str(cache), "FAKE_CURL_MODE": "clean"},
            path_prepend=bin_dir)
    out = r.stdout.strip()
    assert out != "garbage"
    assert HEX16.match(out), out
    # recomputed clean -> the bad entry is overwritten with a real fingerprint
    assert HEX16.match((cache / _key()).read_text().strip())


def test_clean_result_writes_both_stores(tmp_path):
    cache, fb, bin_dir = _dirs(tmp_path)
    r = run(SCRIPT, args=[URL],
            env={"DATASET_CHECKSUM_CACHE": str(cache),
                 "DATASET_CHECKSUM_FALLBACK": str(fb),
                 "FAKE_CURL_MODE": "clean"},
            path_prepend=bin_dir)
    assert r.returncode == 0
    assert HEX16.match(r.stdout.strip())
    assert HEX16.match((cache / _key()).read_text().strip())
    assert HEX16.match((fb / _key()).read_text().strip())


def test_degraded_reuses_valid_fallback(tmp_path):
    cache, fb, bin_dir = _dirs(tmp_path)
    (fb / _key()).write_text("cafebabecafebabe\n")
    r = run(SCRIPT, args=[URL],
            env={"DATASET_CHECKSUM_CACHE": str(cache),
                 "DATASET_CHECKSUM_FALLBACK": str(fb),
                 "FAKE_CURL_MODE": "fail"},
            path_prepend=bin_dir)
    assert r.stdout.strip() == "cafebabecafebabe"
    assert "last-known-good" in r.stderr


def test_degraded_ignores_garbage_fallback(tmp_path):
    cache, fb, bin_dir = _dirs(tmp_path)
    (fb / _key()).write_text("not-a-fingerprint\n")
    r = run(SCRIPT, args=[URL],
            env={"DATASET_CHECKSUM_CACHE": str(cache),
                 "DATASET_CHECKSUM_FALLBACK": str(fb),
                 "FAKE_CURL_MODE": "fail"},
            path_prepend=bin_dir)
    out = r.stdout.strip()
    assert out != "not-a-fingerprint"
    assert HEX16.match(out), out
    assert "last-known-good" not in r.stderr
