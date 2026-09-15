#!/usr/bin/env python3
"""Static graph validation of manifest.yml against the files it references.

A fast, Docker-free gate (audit 2026-09-14, TST-08 recommendation 6): catch a
renamed or missing structure-test config, a dangling alias, or a malformed tag
before the multi-arch build matrix ever starts, the same way the unit and shell
tests catch logic regressions in seconds.

Checks, per context and tag:
  * every path in ``structureTest.configs`` exists on disk;
  * an alias tag (``retagFrom``) points at a real tag in the same context and
    sets ``structureTest: false`` (no build ever produces a local image for it,
    per docs/testing.md);
  * a tag entry is a mapping.

Reports every problem it finds and exits non-zero if there were any. Needs
PyYAML; run as ``python test/validate_manifest.py`` from the repo root (or with a
path argument).
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(manifest_path):
    doc = yaml.safe_load(manifest_path.read_text())
    problems = []
    contexts = (doc or {}).get("contexts", {})
    if not contexts:
        return ["%s: no contexts found" % manifest_path]

    for ctx_name, ctx in contexts.items():
        tags = (ctx or {}).get("tags", {})
        for tag, spec in tags.items():
            where = "%s/%s" % (ctx_name, tag)
            if not isinstance(spec, dict):
                problems.append("%s: tag entry is not a mapping" % where)
                continue

            retag = spec.get("retagFrom")
            if retag is not None:
                if retag not in tags:
                    problems.append(
                        "%s: retagFrom '%s' is not a tag in context '%s'"
                        % (where, retag, ctx_name))
                if spec.get("structureTest") is not False:
                    problems.append(
                        "%s: alias tags must set 'structureTest: false' "
                        "(no image is built for them)" % where)
                continue

            st = spec.get("structureTest")
            if isinstance(st, dict):
                for cfg in st.get("configs", []):
                    if not (ROOT / cfg).is_file():
                        problems.append(
                            "%s: structureTest config not found: %s" % (where, cfg))

    return problems


def main(argv):
    manifest = Path(argv[1]) if len(argv) > 1 else ROOT / "manifest.yml"
    if not manifest.is_file():
        print("validate_manifest: no such file: %s" % manifest, file=sys.stderr)
        return 2
    problems = validate(manifest)
    if problems:
        for p in problems:
            print("manifest: %s" % p, file=sys.stderr)
        print("\n%d problem(s) found in %s" % (len(problems), manifest.name),
              file=sys.stderr)
        return 1
    print("manifest: OK (%s)" % manifest.name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
