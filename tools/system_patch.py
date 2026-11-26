"""Create a GameCube localization ISO for menu and system text."""

import re
import shutil
from collections import Counter
from struct import iter_unpack, pack, pack_into, unpack_from

from PIL import Image, ImageDraw

from font_atlas import ATLAS_ID, DESC_ID, bc1_gray, glyph_font, glyph_tables
from popww_disc import Archive, compressed_stream, disc_files, image, records, text_tables
from text_ppc import install_text_hooks

FONT_WORDS = {
    0x1510: (
        0x801d77ac, 0x801d77bc, 0x801d77dc, 0x801d77fc, 0x801d7894,
        0x801d7934, 0x801d7940, 0x801d8000, 0x801d800c, 0x801d80e0,
        0x801d80f0, 0x801d8120, 0x801d8134, 0x801d8144, 0x801d8168,
        0x801d8174, 0x801d8208,
    ),
    0x150f: (0x801d77b4, 0x801d80e8, 0x801d813c),
    0x150c: (0x801d78a4, 0x801d97fc),
    0x150e: (0x801d78ac, 0x801d985c),
    0x1500: (0x801d78b8,),
    0xff: (0x801d7bb4, 0x801d7e00),
    0xe0: (0x801d8218,),
    0x1c: (0x801d822c,),
}
HANGUL = re.compile(r"[가-힣]")
TAGS = re.compile(rb"<(LABEL|STRING)>([^<]*)</\1>")
SIZE_TABLE_KEY = 0xfc000002
LITERAL_BACKSLASH_GLYPH = 0x357


def widen_font(disc, maximum):
    dol = unpack_from(">I", disc, 0x420)[0]
    section, base = unpack_from(">I", disc, dol + 4)[0], unpack_from(">I", disc, dol + 0x4c)[0]
    if (section, base) != (0x2600, 0x8000edc0):
        raise ValueError("Unexpected G2OE41 executable layout")
    count = maximum + 1 - 0x20
    stride = count * 24 + 16
    replacements = {
        0x1510: stride, 0x150f: stride - 1, 0x150c: stride - 4, 0x150e: stride - 2,
        0x1500: stride - 16, 0xff: maximum, 0xe0: count, 0x1c: count // 8,
    }
    for original, addresses in FONT_WORDS.items():
        for addr in addresses:
            offset = dol + section + addr - base
            word = unpack_from(">I", disc, offset)[0]
            if (word & 0xffff) != original:
                raise ValueError(f"Unexpected instruction at {addr:08x}")
            pack_into(">I", disc, offset, (word & 0xffff0000) | replacements[original])


def build_atlas(texture, description, glyphs, height, preserve_backslash, font):
    width, base_height = unpack_from("<HH", texture, 12)
    if (width, base_height, len(texture)) != (512, 128, 65600):
        raise ValueError("Unexpected font texture")
    bounds = [font.getbbox(char, anchor="ls") for char in glyphs]
    left = min(box[0] for box in bounds) - 1
    top = min(box[1] for box in bounds) - 1
    right = max(box[2] for box in bounds) + 1
    bottom = max(box[3] for box in bounds) + 1
    cell_width, cell_height = right - left, bottom - top
    columns = width // cell_width
    extra = height - base_height
    mask = Image.new("L", (width, extra))
    draw = ImageDraw.Draw(mask)
    rects, bearings = glyph_tables(description)
    scale = base_height / height
    rects = {k: (l, t * scale, r, b * scale) for k, (l, t, r, b) in rects.items()}
    if preserve_backslash:
        rects[LITERAL_BACKSLASH_GLYPH] = rects[ord("\\")]
        bearings[LITERAL_BACKSLASH_GLYPH] = bearings[ord("\\")]
    for idx, (char, code) in enumerate(glyphs.items()):
        x, y = idx % columns * cell_width, idx // columns * cell_height
        if y + cell_height > extra:
            raise ValueError("Hangul atlas overflow")
        draw.text((x - left, y - top), char, font=font, fill=255, anchor="ls")
        rects[code] = (
            x / width, (height - y - cell_height) / height,
            (x + cell_width) / width, (height - y) / height,
        )
        bearings[code] = (left / width, (font.getlength(char) - right) / width)
    plane = width * base_height // 2
    color = texture[60:60 + plane]
    coverage = texture[60 + plane:60 + plane * 2]
    header = bytearray(texture[:60])
    pack_into("<H", header, 14, height)
    pack_into("<I", header, 48, height)
    data = bytes(header) + color + color[:8] * (width * extra // 16) + coverage
    data += bc1_gray(mask.transpose(Image.Transpose.FLIP_TOP_BOTTOM)) + bytes(4)
    coords = b"".join(pack("<Iffff", key, *rect) for key, rect in sorted(rects.items()))
    space = b"".join(pack("<Iff", key, *bearing) for key, bearing in sorted(bearings.items()))
    return data, description[:12] + coords + b"\xff" * 4 + space + b"\xff" * 4


def encode(text, glyphs):
    text = "".join(f"{{{glyphs[c]}}}" if c in glyphs else c for c in text)
    return text.encode("cp1252")


def rewrite_menu(data, translations, glyphs):
    counts = Counter()

    def substitute(match):
        tag, body = match.groups()
        anchor = b"#" if body.startswith(b"#") else b""
        lines = re.split(rb"([\r\n]+)", body[len(anchor):])
        for i in range(0, len(lines), 2):
            source = lines[i].strip().decode("cp1252", "replace")
            if source in translations:
                counts[source] += 1
                lines[i] = encode(translations[source], glyphs)
        return b"<" + tag + b">" + anchor + b"".join(lines) + b"</" + tag + b">"

    return TAGS.sub(substitute, data), counts


def adjust_menu_layout(path, data):
    if path == "/MENU/ENGLISH/P5MAIN.MGM":
        edits = [(b"P_StartNewGame", b"Title", b"<ALIGNMENT>RIGHT</ALIGNMENT>",
                  b"<ALIGNMENT>CENTER</ALIGNMENT>")]
    elif path == "/MENU/ENGLISH/P5COMMON.MGM":
        edits = [
            (b"P_Options", b"Title", b"<ALIGNMENT>RIGHT</ALIGNMENT>", b"<ALIGNMENT>CENTER</ALIGNMENT>"),
            (b"P_MessageBox", b"Text", b"<LEADING>20</LEADING>", b"<LEADING>25</LEADING>"),
        ]
    else:
        return data
    for page, name, before, after in edits:
        pattern = rb"<PAGE>\s*<NAME>" + page + rb"</NAME>(?:(?!</PAGE>).)*?</PAGE>"
        page_match = re.search(pattern, data, re.DOTALL)
        if page_match is None:
            raise ValueError(f"Missing menu page {page!r}")
        pattern = rb"<TEXT>\s*<NAME>" + name + rb"</NAME>.*?</TEXT>"
        text = re.search(pattern, page_match[0], re.DOTALL)
        if text is None or text[0].count(before) != 1:
            raise ValueError(f"Unexpected layout for {page!r}/{name!r}")
        start, end = (page_match.start() + offset for offset in text.span())
        data = data[:start] + text[0].replace(before, after) + data[end:]
    return data


def rewrite_tables(items, translations, glyphs):
    changed = Counter()
    sizes = {}
    for idx, key, text, originals in text_tables(items):
        if (key, text) not in translations:
            continue
        replacements = translations[key, text]
        outputs = list(originals)
        for index, (source, korean) in replacements.items():
            if index < len(originals) and originals[index] == source:
                outputs[index] = encode(korean, glyphs)
                if outputs[index] != source:
                    changed[text, index] += 1
        if outputs == originals:
            continue
        ends = bytearray()
        strings = bytearray()
        for row in outputs:
            ends += pack("<I", len(strings))
            strings += row + b"\0"
        items[idx].data = bytes(ends)
        items[idx + 1].data = bytes(strings)
        sizes[text] = len(strings)
    for item in items:
        data = item.data
        if data[4:8] == b".txi" and len(data) % 8 == 4:
            maximum = unpack_from("<I", data, len(data) - 4)[0]
            expanded = max([maximum] + [
                sizes.get(key, 0) for key, ext in iter_unpack("<I4s", data[:-4])
                if ext == b".txs"
            ])
            if expanded != maximum:
                item.data = data[:-4] + pack("<I", expanded)
    return changed


def patch_streams(disc, source, glyphs, target_offsets, atlas_height, font, font_offsets):
    bf = Archive(source)
    items = records(bf.unpack(min(font_offsets)))
    template = next(r.data for r in items if r.key == ATLAS_ID and len(r.data) > 60)
    descriptor = next(r.data for r in items if r.key == DESC_ID)
    texture, desc = build_atlas(template, descriptor, glyphs, atlas_height, True, font)
    edited = {}
    changed = Counter()
    for offset in sorted(font_offsets | set(target_offsets)):
        original = bf.unpack(offset)
        items = records(original)
        if offset in font_offsets:
            for item in items:
                if item.key == ATLAS_ID:
                    item.data = texture[:60] if len(item.data) == 60 else texture
                elif item.key == DESC_ID:
                    if item.data != descriptor:
                        raise ValueError("Unexpected font descriptor variant")
                    item.data = desc
        if offset in target_offsets:
            changed.update(rewrite_tables(items, target_offsets[offset], glyphs))
        raw = b"".join(item.encode() for item in items)
        if raw == original:
            continue
        edited[offset] = (compressed_stream(raw), raw)

    layout = {}
    end = bf.size
    for offset in reversed(sorted(bf.by_offset)):
        physical = len(bf.slot(offset)) + 4
        if offset in edited:
            required = (len(edited[offset][0]) + 4 + 0x7ff) & ~0x7ff
            physical = max(physical, required)
        layout[offset] = (end - physical, physical)
        end -= physical
    first = min(bf.by_offset)
    if end != first:
        # The sector immediately before the first stream ends in a duplicate
        # of its offset. Preserve the rest of that sector as well.
        guard = 0x800
        prior = bf.base + first - guard
        shifted = bf.base + end - guard
        if end - guard < bf.fat + len(bf.entries) * 8 or any(source[shifted:prior]):
            raise ValueError("Insufficient contiguous space ahead of the archive streams")
        if unpack_from("<I", source, bf.base + first - 4)[0] != first:
            raise ValueError("Unexpected pre-stream sector trailer")
        disc[shifted:shifted + guard] = source[prior:prior + guard - 4] + pack("<I", end)
    for offset, (new, length) in layout.items():
        if offset != new:
            for _, position in bf.by_offset[offset]:
                pack_into("<I", disc, position, new)
        destination = bf.base + new
        if offset in edited:
            payload, _ = edited[offset]
            disc[destination:destination + length] = pack("<I", length - 4) + payload.ljust(length - 4, b"\0")
        elif offset != new:
            original = bf.base + offset
            disc[destination:destination + length] = source[original:original + length]

    size_offset = bf.by_key[SIZE_TABLE_KEY]
    size_original = bf.slot(size_offset)
    size_position = bf.base + layout[size_offset][0] + 4
    sizes = {}
    for pos in range(0, len(size_original) - 7, 8):
        key, length = unpack_from("<II", size_original, pos)
        if key == 0:
            break
        if key in sizes or not 0 < length <= len(bf.slot(bf.by_key[key])) + 4:
            raise ValueError(f"Invalid compressed size table entry {key:08x}")
        sizes[key] = pos + 4
    for offset, (payload, _) in edited.items():
        for key, _ in bf.by_offset[offset]:
            pack_into("<I", disc, size_position + sizes[key], len(payload) + 4)

    check = Archive(disc)
    offsets = list(check.by_offset)
    if offsets != sorted(offsets) or any(
        len(check.slot(a)) + 4 != b - a for a, b in zip(offsets, offsets[1:] + [check.size])
    ):
        raise ValueError("Unexpected rebuilt stream ordering")
    for offset, (_, raw) in edited.items():
        if check.unpack(layout[offset][0]) != raw:
            raise ValueError(f"Archive failed verification at {offset:08x}")
    current_sizes = check.slot(check.by_key[SIZE_TABLE_KEY])
    for offset, (payload, _) in edited.items():
        for key, _ in bf.by_offset[offset]:
            if unpack_from("<I", current_sizes, sizes[key])[0] != len(payload) + 4:
                raise ValueError(f"Archive size table verification failed at {key:08x}")
    print(f"{len(edited)} resource streams verified, archive grew {first - end:,} bytes into padding", flush=True)
    return changed


def build(original_iso, output, inventory, font_offsets, mgm, table_groups, dialogue, font_path):
    targets = {}
    for variant in inventory:
        text = variant["text"]
        key = variant["index"], text
        replacements = dialogue.get((*key, tuple(variant["bytes"])), {})
        if text in table_groups:
            if replacements:
                raise ValueError(f"System and dialogue translations overlap at {text:08x}")
            replacements = table_groups[text]
        if not replacements:
            continue
        streams = {
            int(offset, 16) for offset, ids in variant["streams"].items()
            if any(k.startswith("fd1") for k in ids)
        }
        if not streams:
            continue
        rows = {
            index: (bytes.fromhex(variant["bytes"][index]), korean)
            for index, korean in replacements.items()
        }
        for offset in streams:
            targets.setdefault(offset, {})[key] = rows
    all_strings = list(mgm.values())
    all_strings.extend(ko for group in table_groups.values() for ko in group.values())
    all_strings.extend(ko for group in dialogue.values() for ko in group.values())
    glyphs = {char: idx for idx, char in enumerate(sorted(set(HANGUL.findall("".join(all_strings)))), 256)}
    maximum = LITERAL_BACKSLASH_GLYPH
    height, vertical_scale = 768, 6
    if len(glyphs) > maximum - 256:
        raise ValueError(f"Font needs {len(glyphs)} Hangul glyphs")
    font = glyph_font(20, font_path, glyphs)

    with original_iso.open("rb") as src, output.open("xb") as dest:
        shutil.copyfileobj(src, dest, 8 * 1024 * 1024)
    with image(output, write=True) as disc, image(original_iso) as source_disc:
        widen_font(disc, maximum)
        install_text_hooks(disc, maximum, vertical_scale, cinematic=True)
        changed = patch_streams(disc, source_disc, glyphs, targets, height, font, font_offsets)
        mgm_counts = Counter()
        for path, offset, length, fst in disc_files(disc):
            if not path.startswith("/MENU/ENGLISH/"):
                continue
            original = disc[offset:offset + length]
            data, counts = rewrite_menu(original, mgm, glyphs)
            data = adjust_menu_layout(path, data)
            if len(data) > length:
                data, _ = re.subn(rb"\r(?=\r+\n)", b"", data, count=len(data) - length)
            if len(data) > length:
                raise ValueError(f"Menu package overflow for {path}")
            disc[offset:offset + length] = data.ljust(length, b"\0")
            pack_into(">I", disc, fst + 8, len(data))
            mgm_counts.update(counts)
        disc.flush()
    planned = {(text, index) for text, rows in table_groups.items() for index in rows}
    planned.update((text, index) for (_, text, _), rows in dialogue.items() for index in rows)
    if set(changed) != planned or set(mgm_counts) != set(mgm):
        raise ValueError(f"Missing rows {planned - changed.keys()} or menu entries {mgm.keys() - mgm_counts.keys()}")
    print(f"{len(glyphs)} Hangul glyphs, {sum(mgm_counts.values())} MGM edits, "
          f"{len(changed)} unique archive rows ({sum(changed.values())} copies)", flush=True)
    return glyphs
