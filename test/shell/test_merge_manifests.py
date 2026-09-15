"""TST-05: merge-manifests must bind a done-stamp to the per-arch source digests
it published, so a re-run whose mutable `<tag>-<arch>` sources moved re-merges
the target instead of skipping it and leaving the tag on stale sources.

A fake `curl` stands in for the registry: it answers the auth-token request and,
on a manifest PUT, returns a Docker-Content-Digest equal to the sha256 of the
body (what put_index verifies). merge-manifests reads a tiny throwaway manifest
via `-m`; it needs yq or a Python with PyYAML, so a `python3` shim points at the
test interpreter when yq is absent, and the module skips if neither is available.
"""
import json
import shutil
import subprocess
import sys

import pytest
from shellkit import fake_bin, run, requires_shell

pytestmark = requires_shell


def _yaml_reader():
    if shutil.which("yq"):
        return True
    try:
        subprocess.run([sys.executable, "-c", "import yaml"], check=True,
                       capture_output=True)
        return True
    except Exception:
        return False


needs_yaml = pytest.mark.skipif(
    not _yaml_reader(),
    reason="merge-manifests needs yq or a Python with PyYAML to read the manifest",
)

MANIFEST = """\
parameters:
  repository: test/repo
  platforms: linux/amd64,linux/arm64
contexts:
  demo:
    tags:
      iso3166: {}
"""

# Fake registry: token GET + manifest PUT (echo back sha256(body) as the digest).
FAKE_CURL = r'''
args=("$@"); url="${args[$((${#args[@]}-1))]}"
case "$url" in
  *auth.docker.io/token*) cat >/dev/null 2>&1 || true; printf '{"token":"faketoken"}'; exit 0 ;;
esac
hdr=""; body=""; i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in
    -D) hdr="${args[$((i+1))]}" ;;
    --data-binary) body="${args[$((i+1))]#@}" ;;
  esac
  i=$((i+1))
done
if [ -n "$hdr" ] && [ -n "$body" ]; then
  if command -v sha256sum >/dev/null 2>&1; then d="$(sha256sum "$body" | cut -d' ' -f1)"
  else d="$(shasum -a 256 "$body" | cut -d' ' -f1)"; fi
  printf 'HTTP/1.1 201 Created\r\nDocker-Content-Digest: sha256:%s\r\n\r\n' "$d" > "$hdr"
  exit 0
fi
exit 1
'''

D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
D3 = "sha256:" + "c" * 64


def _descriptor(arch, digest):
    return {
        "repository": "test/repo", "tag": "iso3166", "target": "iso3166-%s" % arch,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "digest": digest, "size": 1234,
        "platform": {"os": "linux", "architecture": arch},
    }


def _setup(tmp_path, amd_digest, arm_digest):
    desc = tmp_path / "desc"; desc.mkdir(exist_ok=True)
    (desc / "test-repo-iso3166-amd64.json").write_text(json.dumps(_descriptor("amd64", amd_digest)))
    (desc / "test-repo-iso3166-arm64.json").write_text(json.dumps(_descriptor("arm64", arm_digest)))
    man = tmp_path / "manifest.yml"; man.write_text(MANIFEST)
    bind = tmp_path / "bin"; bind.mkdir(exist_ok=True)
    fake_bin(bind, "curl", FAKE_CURL)
    fake_bin(bind, "python3", 'exec "%s" "$@"' % sys.executable)
    stamps = tmp_path / "stamps"; stamps.mkdir(exist_ok=True)
    return desc, man, bind, stamps


def _env(desc, stamps):
    return {"DESCRIPTOR_DIR": str(desc), "MERGE_STAMP_DIR": str(stamps),
            "DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t"}


def _merge(man, bind, desc, stamps):
    return run("bin/merge-manifests", args=["-c", "demo", "-m", str(man)],
               env=_env(desc, stamps), path_prepend=bind)


@needs_yaml
def test_merge_puts_and_stamps_signature(tmp_path):
    desc, man, bind, stamps = _setup(tmp_path, D1, D2)
    r = _merge(man, bind, desc, stamps)
    assert r.returncode == 0, r.stderr
    assert "test/repo:iso3166 <-" in r.stderr
    stamp = stamps / "test-repo-iso3166"
    assert stamp.exists()
    assert stamp.read_text().strip() == "amd64=%s,arm64=%s" % (D1, D2)


@needs_yaml
def test_unchanged_sources_skip(tmp_path):
    desc, man, bind, stamps = _setup(tmp_path, D1, D2)
    _merge(man, bind, desc, stamps)
    r = _merge(man, bind, desc, stamps)
    assert r.returncode == 0, r.stderr
    assert "already merged from identical sources; skipping" in r.stderr


@needs_yaml
def test_moved_source_digest_remerges(tmp_path):
    desc, man, bind, stamps = _setup(tmp_path, D1, D2)
    _merge(man, bind, desc, stamps)
    # amd64 source image changed under the same mutable tag -> new digest.
    _setup(tmp_path, D3, D2)
    r = _merge(man, bind, desc, stamps)
    assert r.returncode == 0, r.stderr
    assert "skipping" not in r.stderr
    assert "test/repo:iso3166 <-" in r.stderr
    assert (stamps / "test-repo-iso3166").read_text().strip() == "amd64=%s,arm64=%s" % (D3, D2)
