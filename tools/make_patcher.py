"""Package a file-level GameCube patch from the local original and Korean ISOs."""

import argparse
import csv
import hashlib
import os
import shutil
from pathlib import Path
from struct import pack_into, unpack_from
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pyxdelta

from popww_disc import disc_files, image

ROOT = Path(__file__).resolve().parents[1]
WIT_FILES = (
    "wit.exe", "cygwin1.dll", "cygz.dll", "cygcrypto-1.1.dll", "cygncursesw-10.dll",
)
FIELDS = ("kind", "path", "size", "source_sha256", "target_sha256", "delta")
DISC_SIZE = 1459978240


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def dol_bounds(disc):
    base = unpack_from(">I", disc, 0x420)[0]
    offsets = unpack_from(">18I", disc, base)
    sizes = unpack_from(">18I", disc, base + 0x90)
    return base, offsets, sizes


def check_unchanged(before, after, changed):
    end = 0
    for start, stop in sorted(changed) + [(len(before), len(before))]:
        if start < end:
            raise ValueError("Overlapping patch regions")
        for offset in range(end, start, 8 * 1024 * 1024):
            boundary = min(start, offset + 8 * 1024 * 1024)
            if before[offset:boundary] != after[offset:boundary]:
                raise ValueError(f"Unexpected change outside file patches at {offset:#x}")
        end = stop


def write_deltas(original, localized, output, scratch):
    manifest = []
    source_file = scratch / "source.bin"
    target_file = scratch / "patched.bin"

    def add(kind, path, source, target):
        if len(source) != len(target):
            raise ValueError(f"{path} exceeds its original allocation")
        name = f"{len(manifest):03d}.xdelta"
        source_file.write_bytes(source)
        target_file.write_bytes(target)
        cwd = Path.cwd()
        try:
            os.chdir(scratch)
            if not pyxdelta.run(source_file.name, target_file.name, "delta.xdelta"):
                raise RuntimeError(f"Could not encode delta for {path}")
        finally:
            os.chdir(cwd)
        (scratch / "delta.xdelta").replace(output / name)
        manifest.append((kind, path, len(source), digest(source), digest(target), name))
        print(f"{name} {path}", flush=True)

    with image(original) as before, image(localized) as after:
        if before[:8] != b"G2OE41\0\0" or before[:8] != after[:8] or len(before) != len(after):
            raise ValueError("Expected a matching pair of G2OE41 revision 0 ISOs")
        if len(before) != DISC_SIZE:
            raise ValueError("Use the full-sized ISO to build the patch")
        dol, offsets, sizes = dol_bounds(before)
        new_dol, new_offsets, new_sizes = dol_bounds(after)
        if dol != new_dol or offsets[2] or sizes[2] or not new_sizes[2] or any(
            (a, b) != (c, d)
            for i, (a, b, c, d) in enumerate(zip(offsets, sizes, new_offsets, new_sizes))
            if i != 2
        ):
            raise ValueError("Unexpected executable layout changes")
        dol_end = dol + max(o + s for o, s in zip(offsets, sizes) if s)
        hook = dol + new_offsets[2]
        hook_end = hook + new_sizes[2]
        dol_target = bytearray(after[dol:dol_end])
        # The applier sets this section's offset relative to the input DOL.
        pack_into(">I", dol_target, 0x08, 0)
        add("dol", "main.dol", before[dol:dol_end], dol_target)
        add("hook", "text-hook", bytes(new_sizes[2]), after[hook:hook_end])
        changed = [(dol, dol_end), (hook, hook_end)]
        raw_before = {path: (offset, size) for path, offset, size, _ in disc_files(before)}
        raw_after = {path: (offset, size) for path, offset, size, _ in disc_files(after)}
        if raw_before != raw_after:
            raise ValueError("Unexpected disc file layout changes")
        for path, (start, length) in raw_before.items():
            end = start + length
            source, target = before[start:end], after[start:end]
            if source != target:
                add("file", path, source, target)
                changed.append((start, end))
        check_unchanged(before, after, changed)

    with (output / "manifest.txt").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t", lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("localized", type=Path)
    parser.add_argument("--wit", type=Path, required=True, help="Folder containing wit.exe and its DLLs")
    parser.add_argument("--xdelta", type=Path, required=True, help="Bundled xdelta3 executable")
    parser.add_argument("--out", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    version = "0.9"
    name = f"G2OE_KPatch_v{version}"
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".popww-release-", dir=output) as temporary:
        stage = Path(temporary)
        package = stage / name
        data = package / "data"
        binaries = package / "bin"
        data.mkdir(parents=True)
        binaries.mkdir()
        write_deltas(args.original.resolve(), args.localized.resolve(), data, stage)
        (data / "config.txt").write_text(
            f"id=G2OE41\nrev=0\nversion={version}\ndisc_size={DISC_SIZE}\n", encoding="ascii"
        )
        for file in ("README.txt", "patch.ps1"):
            source = ROOT / "patcher" / file
            (package / file).write_text(source.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        batch = (ROOT / "patcher" / "패치하기.bat").read_text(encoding="ascii")
        (package / "패치하기.bat").write_bytes(batch.replace("\n", "\r\n").encode("ascii"))
        for file in WIT_FILES:
            shutil.copyfile(args.wit / file, binaries / file)
        shutil.copyfile(args.wit / "GPL-2.0.txt", binaries / "wit-gpl-2.0.txt")
        shutil.copyfile(args.xdelta, binaries / "xdelta3.exe")
        zip_path = stage / f"{name}.zip"
        with ZipFile(zip_path, "w", ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(package.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(stage).as_posix())
        checksum = sha256(zip_path)
        zip_path.replace(output / zip_path.name)
        (output / f"SHA256SUMS_v{version}.txt").write_bytes(
            f"{checksum}  {zip_path.name}\n".encode("ascii")
        )
        for file in sorted(data.iterdir()):
            tracked = ROOT / "patcher" / "data"
            tracked.mkdir(exist_ok=True)
            shutil.copyfile(file, tracked / file.name)
    print(f"{zip_path.name} {checksum}", flush=True)


if __name__ == "__main__":
    main()
