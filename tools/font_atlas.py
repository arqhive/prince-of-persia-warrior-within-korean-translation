"""Read Jade font metrics and encode grayscale coverage for GameCube."""

from io import BytesIO
from struct import iter_unpack, unpack_from

import numpy as np
from fontTools.ttLib import TTFont
from PIL import ImageFont

ATLAS_ID = 0x2f008574
DESC_ID = 0x0900094e


def glyph_tables(description):
    rows = {}
    cursor = 12
    while unpack_from("<I", description, cursor)[0] != 0xffffffff:
        key, *rect = unpack_from("<Iffff", description, cursor)
        rows[key] = tuple(rect)
        cursor += 20
    metrics = {key: (left, right) for key, left, right in iter_unpack("<Iff", description[cursor + 4:-4])}
    if rows.keys() != metrics.keys() or description[-4:] != b"\xff" * 4:
        raise ValueError("Unexpected font metrics")
    return rows, metrics


def glyph_font(size, path, characters):
    data = BytesIO()
    with TTFont(path) as font:
        available = font.getBestCmap()
        missing = [char for char in characters if ord(char) not in available]
        if missing:
            raise ValueError(f"Font is missing these glyphs: {''.join(missing)}")
        font.flavor = None
        font.save(data)
    data.seek(0)
    return ImageFont.truetype(data, size)


def bc1_gray(image):
    pixels = np.asarray(image, dtype=np.uint16)
    indices = np.array([1, 3, 2, 0], dtype=np.uint8)[(pixels + 42) // 85]
    blocks = indices.reshape(image.height // 4, 4, image.width // 4, 4).transpose(0, 2, 1, 3)
    packed = np.sum(blocks << np.arange(0, 8, 2, dtype=np.uint8), axis=3).astype(np.uint8)
    encoded = np.empty((*blocks.shape[:2], 8), dtype=np.uint8)
    encoded[:, :, :4] = [255, 255, 0, 0]
    encoded[:, :, 4:] = packed
    return encoded.tobytes()
