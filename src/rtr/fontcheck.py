from __future__ import absolute_import, unicode_literals

import struct

CYRILLIC_PROBE = (0x0416, 0x0436, 0x044B)


def _u16(data, pos):
    return struct.unpack(">H", data[pos:pos + 2])[0]


def _u32(data, pos):
    return struct.unpack(">I", data[pos:pos + 4])[0]


def _font_offset(data):
    if data[:4] == b"ttcf":
        return _u32(data, 12)
    return 0


def _cmap_offset(data, base):
    count = _u16(data, base + 4)
    for i in range(count):
        rec = base + 12 + i * 16
        if data[rec:rec + 4] == b"cmap":
            return _u32(data, rec + 8)
    return None


def _format4_has(data, pos, code):
    segcount = _u16(data, pos + 6) // 2
    ends = pos + 14
    starts = ends + segcount * 2 + 2
    deltas = starts + segcount * 2
    ranges = deltas + segcount * 2
    for i in range(segcount):
        end = _u16(data, ends + i * 2)
        if code > end:
            continue
        start = _u16(data, starts + i * 2)
        if code < start:
            return False
        offset = _u16(data, ranges + i * 2)
        if offset == 0:
            return (code + _u16(data, deltas + i * 2)) & 0xFFFF != 0
        glyph_pos = ranges + i * 2 + offset + (code - start) * 2
        return _u16(data, glyph_pos) != 0
    return False


def _format12_has(data, pos, code):
    groups = _u32(data, pos + 12)
    for i in range(groups):
        g = pos + 16 + i * 12
        if _u32(data, g) <= code <= _u32(data, g + 4):
            return True
    return False


def has_chars(data, codes):
    base = _font_offset(data)
    cmap = _cmap_offset(data, base)
    if cmap is None:
        return False
    count = _u16(data, cmap + 2)
    for i in range(count):
        rec = cmap + 4 + i * 8
        platform = _u16(data, rec)
        encoding = _u16(data, rec + 2)
        if (platform, encoding) not in ((3, 1), (3, 10), (0, 3), (0, 4), (0, 6)):
            continue
        sub = cmap + _u32(data, rec + 4)
        fmt = _u16(data, sub)
        if fmt == 4:
            check = _format4_has
        elif fmt == 12:
            check = _format12_has
        else:
            continue
        if all(check(data, sub, c) for c in codes):
            return True
    return False


def has_cyrillic(data):
    try:
        return has_chars(data, CYRILLIC_PROBE)
    except (struct.error, IndexError):
        return False
