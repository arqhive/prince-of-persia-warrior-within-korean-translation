"""Read the GameCube Warrior Within disc and Jade resource streams."""

import mmap
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from struct import iter_unpack, pack, unpack_from

import lzokay

RECORD_MAGIC = 0xeeffc099


@contextmanager
def image(path, write=False):
    with Path(path).open("r+b" if write else "rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_WRITE if write else mmap.ACCESS_READ) as data:
            yield data


def disc_files(data):
    if data[:8] != b"G2OE41\0\0":
        raise ValueError("Expected GameCube G2OE41 revision 0")
    start, length = unpack_from(">II", data, 0x424)
    table = data[start:start + length]
    count = unpack_from(">I", table, 8)[0]
    directories = [("", count)]
    for idx in range(1, count):
        flag, offset, size = unpack_from(">III", table, idx * 12)
        name_offset = 12 * count + (flag & 0xffffff)
        name = table[name_offset:table.index(0, name_offset)].decode("ascii")
        while idx >= directories[-1][1]:
            directories.pop()
        path = directories[-1][0] + "/" + name
        if flag >> 24:
            directories.append((path, size))
        else:
            yield path, offset, size, start + idx * 12


class Archive:
    def __init__(self, data):
        self.data = data
        self.base, self.size, self.fst_entry = next(
            (off, size, entry) for name, off, size, entry in disc_files(data) if name == "/prince.bf"
        )
        magic, version, count = unpack_from("<4sII", data, self.base)
        if (magic, version) != (b"BIG\0", 38):
            raise ValueError("Unexpected Jade BIG format")
        self.fat = unpack_from("<I", data, self.base + 0x34)[0]
        start = self.base + self.fat
        self.entries = list(iter_unpack("<II", data[start:start + 8 * count]))
        self.by_key = {key: offset for offset, key in self.entries}
        self.by_offset = defaultdict(list)
        for idx, (offset, key) in enumerate(self.entries):
            self.by_offset[offset].append((key, start + idx * 8))

    def slot(self, offset):
        start = self.base + offset
        size = unpack_from("<I", self.data, start)[0]
        if not 0 < size <= self.size - offset - 4:
            raise ValueError(f"Invalid chunk size at {offset:08x}")
        return self.data[start + 4:start + 4 + size]

    def unpack(self, offset):
        encoded = self.slot(offset)
        cursor = 0
        result = bytearray()
        while cursor + 8 <= len(encoded):
            raw, compressed = unpack_from("<II", encoded, cursor)
            if raw == 0:
                break
            cursor += 8
            if not 0 < compressed <= raw <= 0x20000 or cursor + compressed > len(encoded):
                raise ValueError(f"Unsupported block at {offset:08x}+{cursor - 8:x}")
            payload = encoded[cursor:cursor + compressed]
            if compressed == raw:
                result.extend(payload)
            else:
                try:
                    result.extend(lzokay.decompress(payload, raw))
                except lzokay.LzokayError as err:
                    raise ValueError(f"Invalid compressed block at {offset:08x}+{cursor - 8:x}") from err
            cursor += compressed
        return bytes(result)


@dataclass
class Record:
    key: int
    data: bytes

    def encode(self):
        return pack("<III", len(self.data), RECORD_MAGIC, self.key) + self.data


def records(data):
    result = []
    cursor = 0
    while cursor < len(data):
        length, magic, key = unpack_from("<III", data, cursor)
        end = cursor + 12 + length
        if magic != RECORD_MAGIC or end > len(data):
            raise ValueError(f"Unexpected record at {cursor:x}")
        result.append(Record(key, data[cursor + 12:end]))
        cursor = end
    return result


def text_tables(items):
    extensions = defaultdict(set)
    for record in items:
        if record.data[4:8] in (b".txi", b".txg"):
            for key, extension in iter_unpack("<I4s", record.data[:len(record.data) // 8 * 8]):
                extensions[key].add(extension)
    for idx, (index, text) in enumerate(zip(items, items[1:])):
        if b".txi" not in extensions[index.key] or b".txs" not in extensions[text.key]:
            continue
        if not index.data or len(index.data) % 4:
            continue
        offsets = [row[0] for row in iter_unpack("<I", index.data)] + [len(text.data)]
        if offsets[0] != 0 or any(
            a >= b or b > len(text.data) or text.data[b - 1] for a, b in zip(offsets, offsets[1:])
        ):
            continue
        yield idx, index.key, text.key, [text.data[a:b - 1] for a, b in zip(offsets, offsets[1:])]


def compressed_stream(data):
    result = bytearray()
    for offset in range(0, len(data), 0x20000):
        block = data[offset:offset + 0x20000]
        encoded = lzokay.compress(block)
        if lzokay.decompress(encoded, len(block)) != block:
            raise ValueError("LZO verification failed")
        result += pack("<II", len(block), len(encoded)) + encoded
    return bytes(result)
