"""PowerPC hooks for the GameCube 16-bit glyphs and atlas coordinates."""

from struct import pack, pack_into, unpack_from

from popww_disc import disc_files

CODE_ADDRESS = 0x80002900
TEXT_OFFSET = 0x2600
TEXT_ADDRESS = 0x8000edc0


def branch(source, destination, link=False):
    displacement = destination - source
    if displacement % 4 or not -0x2000000 <= displacement < 0x2000000:
        raise ValueError("PowerPC branch out of range")
    return 0x48000000 | (displacement & 0x3fffffc) | int(link)


def compare(register, value):
    return 0x28000000 | (register << 16) | (value & 0xffff)


def rlwinm(dst, src, shift, low, high):
    return 0x54000000 | (src << 21) | (dst << 16) | (shift << 11) | (low << 6) | (high << 1)


def ori_register(dst, left, right):
    return 0x7c000378 | (left << 21) | (dst << 16) | (right << 11)


class Code:
    def __init__(self, address):
        self.address = address
        self.instructions = []
        self.labels = {}
        self.jumps = []

    @property
    def pc(self):
        return self.address + 4 * len(self.instructions)

    def emit(self, *words):
        self.instructions.extend(words)

    def mark(self, label):
        self.labels[label] = self.pc

    def jump(self, target, opcode=0x48000000):
        if isinstance(target, int) and opcode in (0x48000000, 0x48000001):
            self.emit(branch(self.pc, target, link=bool(opcode & 1)))
        else:
            self.jumps.append((self.pc, target, opcode))
            self.emit(0)

    def finish(self):
        for address, label, opcode in self.jumps:
            distance = self.labels[label] - address
            if opcode == 0x48000000:
                word = branch(address, self.labels[label])
            else:
                if not -32768 <= distance < 32768:
                    raise ValueError("Conditional branch out of range")
                word = opcode | (distance & 0xfffc)
            self.instructions[(address - self.address) // 4] = word
        return pack(f">{len(self.instructions)}I", *self.instructions)


def decode_ascii_glyph(code, maximum):
    """Read the three decimal digits without consuming non-glyph braces."""
    code.mark("decode_glyph")
    for i in range(1, 4):
        code.emit(0x88830000 | i)                    # lbz r4, i(r3)
        code.emit(0x3884ffd0, compare(4, 9))        # addi r4, r4, -48
        code.jump("invalid_glyph", 0x41810000)       # bgt
        if i == 1:
            code.emit(0x7c852378)                  # mr r5, r4
        else:
            code.emit(0x1ca5000a, 0x7ca52214)       # mulli r5, r5, 10 / add r5, r5, r4
    code.emit(0x88830004, compare(4, 0x7d))
    code.jump("invalid_glyph", 0x40820000)
    code.emit(compare(5, 0x100))
    code.jump("invalid_glyph", 0x41800000)
    code.emit(compare(5, maximum))
    code.jump("invalid_glyph", 0x41810000)
    code.emit(0x7ca32b78, 0x4e800020)                # mr r3, r5 / blr
    code.mark("invalid_glyph")
    code.emit(0x38600000, 0x4e800020)


def install_text_hooks(disc, maximum, vertical_scale=4, cinematic=False):
    """Decode Hangul in text renderers and correct the enlarged atlas geometry."""
    dol = unpack_from(">I", disc, 0x420)[0]
    fst, fst_size = unpack_from(">II", disc, 0x424)
    patch_file = (fst + fst_size + 0x1ff) & ~0x1ff
    code = Code(CODE_ADDRESS)
    hooks = {}

    def hook(address, original):
        hooks[address] = (original, code.pc)

    if vertical_scale not in (4, 5, 6):
        raise ValueError("Unsupported atlas scale")
    for address, displaced, fpr, font in (
        (0x80026ac0, 0xef6f8028, 27, 31), (0x80027448, 0xec529828, 2, 31),
        (0x801d9918, 0xec810028, 4, 4),
    ):
        hook(address, displaced)
        double = 0xec00002a | (fpr << 21) | (fpr << 16) | (fpr << 11)
        scaling = (double, double)
        if vertical_scale in (5, 6):
            save = 0xfc000090 | (fpr << 11)           # fmr f0, glyph height
            add = 0xec00002a | (fpr << 21) | (fpr << 16)
            scaling = (save, double, double, add) if vertical_scale == 5 else (double, save, double, add)
        code.emit(
            displaced,
            0x80000000 | (font << 16),             # lwz r0, 0(font)
            0x3d802f00, 0x618c8574,                # texture resource 0x2f008574
            0x7c006000, 0x40820000 | (4 * (len(scaling) + 1)),
            *scaling,
        )
        code.jump(address + 4)

    decode_ascii_glyph(code, maximum)
    decoder_address = code.labels["decode_glyph"]
    if cinematic:
        # Replace the movie renderer's byte-to-wide-character copy.
        # r3 holds the capped byte length, r28 is input and r29 is output.
        hook(0x801a9ffc, 0x38800000)
        code.emit(0x7c661b78)                      # mr r6, r3
        code.mark("movie_next")
        code.emit(compare(6, 0))
        code.jump("movie_end", 0x41820000)
        code.emit(0x881c0000, compare(0, 0x7b))   # lbz r0, 0(r28)
        code.jump("movie_write", 0x40820000)
        code.emit(compare(6, 5))
        code.jump("movie_write", 0x41800000)
        code.emit(0x7f83e378)                      # mr r3, r28
        code.jump(decoder_address, 0x48000001)
        code.emit(compare(3, 0))
        code.jump("movie_write", 0x41820000)
        code.emit(0x7c601b78, 0x3b9c0004, 0x38c6fffc)
        code.mark("movie_write")
        code.emit(0xb01d0000, 0x3bbd0002, 0x3b9c0001, 0x38c6ffff)
        code.jump("movie_next")
        code.mark("movie_end")
        code.jump(0x801aa0e8)

    hook(0x801d83a8, 0x2c00005c)
    code.emit(compare(0, 0x7b))
    code.jump("original_parse", 0x40820000)
    code.emit(0x7e639b78)                           # mr r3, r19
    code.jump(decoder_address, 0x48000001)
    code.emit(compare(3, 0))
    code.jump("original_parse", 0x41820000)
    # The page actually uses only the low part of its byte. Keep its six
    # low bits and use its two high bits for the extra glyph index.
    code.emit(rlwinm(29, 3, 0, 24, 31), rlwinm(3, 3, 6, 16, 17),
              ori_register(29, 29, 3), 0x3b800001, 0x3a730005)
    code.jump(0x801d8534)
    code.mark("original_parse")
    code.emit(0x2c00005c)
    code.jump(0x801d83ac)

    hook(0x801d87b4, 0x2c00000d)
    code.emit(compare(0, 0x7b))
    code.jump("original_count", 0x40820000)
    code.emit(0x7f83e378)                           # mr r3, r28
    code.jump(decoder_address, 0x48000001)
    code.emit(compare(3, 0))
    code.jump("original_count", 0x41820000)
    code.emit(0x3b9c0004)
    code.jump(0x801d87e4)
    code.mark("original_count")
    code.emit(0x2c00000d)
    code.jump(0x801d87b8)

    for address in (0x801d5f88, 0x801d60ac, 0x801d97b8, 0x801d98e8, 0x801dfb10):
        hook(address, 0x5403063e)
        code.emit(rlwinm(3, 0, 0, 24, 31), rlwinm(12, 0, 26, 22, 23), ori_register(3, 3, 12))
        code.jump(address + 4)

    payload = code.finish()
    first_file = min(offset for _, offset, _, _ in disc_files(disc))
    if patch_file + len(payload) > first_file or CODE_ADDRESS + len(payload) > 0x80003000:
        raise ValueError("No space for extra DOL section")
    for field, value in ((0x08, patch_file - dol), (0x50, CODE_ADDRESS), (0x98, len(payload))):
        if unpack_from(">I", disc, dol + field)[0] != 0:
            raise ValueError("DOL text section slot is occupied")
        pack_into(">I", disc, dol + field, value)
    disc[patch_file:patch_file + len(payload)] = payload
    for address, (expected, target) in {
        **hooks, 0x801d8548: (0x57a0063e, None),
    }.items():
        offset = dol + TEXT_OFFSET + address - TEXT_ADDRESS
        if unpack_from(">I", disc, offset)[0] != expected:
            raise ValueError(f"Unexpected text instruction at {address:08x}")
        replacement = 0x7fa0eb78 if target is None else branch(address, target)
        pack_into(">I", disc, offset, replacement)
    page_readers = {
        0x54a5042e: (0x801d5938, 0x801d5990, 0x801d59b8, 0x801d59e0, 0x801d5a08, 0x801d5a48),
        0x5400042e: (0x801d5f54, 0x801d6080, 0x801d974c, 0x801dfad4),
        0x5480042e: (0x801d9dd8, 0x801d9e30),
    }
    for expected, addresses in page_readers.items():
        for address in addresses:
            offset = dol + TEXT_OFFSET + address - TEXT_ADDRESS
            if unpack_from(">I", disc, offset)[0] != expected:
                raise ValueError(f"Unexpected page instruction at {address:08x}")
            pack_into(">I", disc, offset, expected + 0x80)  # rlwinm mask starts at bit 18
