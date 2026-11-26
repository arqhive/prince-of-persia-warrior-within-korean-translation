"""Rebuild the Korean patch from a verified North American GameCube ISO."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from font_atlas import DESC_ID
from popww_disc import Archive, disc_files, image, records, text_tables
from system_patch import LITERAL_BACKSLASH_GLYPH, TAGS, build, encode

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "translations" / "ko"
TIMING = re.compile(rb"^\s*\(\s*-?\d+\s*[,.]\s*-?\d+\s*\)")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_disc(original, menu_rows):
    variants = {}
    font_offsets = set()
    menu = {}
    with image(original) as disc:
        for path, offset, size, _ in disc_files(disc):
            if not path.startswith("/MENU/ENGLISH/"):
                continue
            resource = menu_rows.pop(path.rsplit("/", 1)[-1], {})
            tags = list(TAGS.finditer(disc[offset:offset + size]))
            for address, korean in resource.items():
                tag, line = map(int, address.split(":"))
                body = tags[tag][2].removeprefix(b"#")
                english = re.split(rb"[\r\n]+", body)[line].strip().decode("cp1252", "replace")
                if menu.setdefault(english, korean) != korean:
                    raise ValueError(f"Conflicting menu translations at {path} {address}")
        if menu_rows:
            raise ValueError(f"Missing menu resources: {list(menu_rows)}")

        archive = Archive(disc)
        for offset, owners in archive.by_offset.items():
            try:
                items = records(archive.unpack(offset))
            except ValueError:
                continue
            if any(row.key == DESC_ID and row.data.startswith(b"FONTDESC") for row in items):
                font_offsets.add(offset)
            keys = [f"{key:08x}" for key, _ in owners if key >> 20 == 0xfd1]
            if not keys:
                continue
            for _, index, text, rows in text_tables(items):
                raw = tuple(row.hex() for row in rows)
                variant = variants.setdefault((index, text, raw), {
                    "index": index, "text": text, "bytes": raw, "streams": {},
                })
                variant["streams"][f"{offset:08x}"] = keys
    return menu, list(variants.values()), font_offsets


def compile_dialogue(inventory, source):
    translations = {}
    found = set()
    for variant in inventory:
        index, text, raw = variant["index"], variant["text"], variant["bytes"]
        resource = f"{index:08x}/{text:08x}"
        if resource not in source:
            continue
        found.add(resource)
        rows = {}
        for key, korean in source[resource].items():
            line = int(key)
            stamp = TIMING.match(bytes.fromhex(raw[line]))
            if not stamp:
                raise ValueError(f"Missing original caption timing at {resource} row {line}")
            body = korean.replace("\\", f"{{{LITERAL_BACKSLASH_GLYPH}}}").replace("\n", r"\n")
            rows[line] = stamp[0].decode("ascii") + body
        translations[index, text, raw] = rows
    if found != source.keys():
        raise ValueError(f"Missing subtitle resources: {source.keys() - found}")
    return translations


def verify_subtitles(original, output, inventory, dialogue, glyphs):
    checked = {}
    with image(original) as before, image(output) as after:
        source, patched = Archive(before), Archive(after)
        for variant in inventory:
            key = variant["index"], variant["text"]
            raw = variant["bytes"]
            rows = dialogue.get((*key, raw))
            if rows is None:
                continue
            expected = [
                encode(rows[i], glyphs) if i in rows else bytes.fromhex(value)
                for i, value in enumerate(raw)
            ]
            for old_offset in variant["streams"]:
                offset = int(old_offset, 16)
                if offset not in checked:
                    owner = next(key for key, _ in source.by_offset[offset] if key >> 20 == 0xfd1)
                    items = records(patched.unpack(patched.by_key[owner]))
                    checked[offset] = {(i, t): lines for _, i, t, lines in text_tables(items)}
                if checked[offset].get(key) != expected:
                    raise ValueError(f"Subtitle verification failed at {key} in {offset:08x}")
    print(f"Verified subtitles and original timing in {len(checked)} English streams")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="Verified G2OE41 revision 0 ISO")
    parser.add_argument("output", type=Path, help="New ISO path")
    parser.add_argument("--font", type=Path, required=True, help="Local Warhaven Regular font file")
    args = parser.parse_args()
    manifest = read_json(ROOT / "patcher" / "manifest.json")
    with args.original.open("rb") as stream:
        original_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if original_hash != manifest["source_sha256"]:
        parser.error("Original ISO SHA-256 differs from the verified G2OE41 image")
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    menu, inventory, fonts = read_disc(args.original, read_json(TRANSLATIONS / "menu.json"))
    system = {
        int(key, 16): {int(i): text for i, text in rows.items()}
        for key, rows in read_json(TRANSLATIONS / "system.json").items()
    }
    dialogue = compile_dialogue(inventory, read_json(TRANSLATIONS / "dialogue.json"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".popww-build-", dir=args.output.parent) as stage:
        temporary_iso = Path(stage) / "korean.iso"
        glyphs = build(args.original, temporary_iso, inventory, fonts, menu, system, dialogue, args.font)
        verify_subtitles(args.original, temporary_iso, inventory, dialogue, glyphs)
        temporary_iso.rename(args.output)
    with args.output.open("rb") as stream:
        print(f"SHA-256 {hashlib.file_digest(stream, 'sha256').hexdigest()}")


if __name__ == "__main__":
    main()
