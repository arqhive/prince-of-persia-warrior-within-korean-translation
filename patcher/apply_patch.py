"""Apply the verified Warrior Within Korean xdelta patch to a clean ISO."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pyxdelta


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, patch, output = (path.resolve() for path in (args.original, args.patch, args.output))
    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    if output.exists():
        parser.error(f"Output already exists: {output}")
    if source.stat().st_size != manifest["iso_size"] or sha256(source) != manifest["source_sha256"]:
        parser.error("Original ISO does not match G2OE41 revision 0")
    if sha256(patch) != manifest["patch_sha256"]:
        parser.error(f"Patch SHA-256 does not match release {manifest['version']}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".popww-patch-", dir=output.parent) as scratch:
        stage = Path(scratch)
        # The Windows xdelta binding expects narrow filenames. A local stage
        # lets it use ASCII names even inside folders with Korean names.
        shutil.copyfile(source, stage / "source.iso")
        shutil.copyfile(patch, stage / "patch.xdelta")
        cwd = Path.cwd()
        try:
            os.chdir(stage)
            if not pyxdelta.decode("source.iso", "patch.xdelta", "korean.iso"):
                raise RuntimeError("xdelta could not decode the patch")
        finally:
            os.chdir(cwd)
        result = stage / "korean.iso"
        if result.stat().st_size != manifest["iso_size"] or sha256(result) != manifest["result_sha256"]:
            raise ValueError("Result ISO SHA-256 does not match the release")
        result.rename(output)
    print(f"Created {output}\nSHA-256 {manifest['result_sha256']}")


if __name__ == "__main__":
    main()
