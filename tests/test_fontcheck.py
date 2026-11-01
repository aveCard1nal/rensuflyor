from __future__ import unicode_literals

import struct
import unittest

from rtr.fontcheck import has_chars, has_cyrillic


def format4(segments):
    segments = list(segments) + [(0xFFFF, 0xFFFF, 1)]
    n = len(segments)
    ends = b"".join(struct.pack(">H", e) for s, e, d in segments)
    starts = b"".join(struct.pack(">H", s) for s, e, d in segments)
    deltas = b"".join(struct.pack(">h", d) for s, e, d in segments)
    ranges = b"\0\0" * n
    body = struct.pack(">HHHH", n * 2, 0, 0, 0) + ends + b"\0\0" + starts + deltas + ranges
    return struct.pack(">HHH", 4, 6 + len(body), 0) + body


def format12(groups):
    body = b"".join(struct.pack(">III", s, e, 1) for s, e in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def font(subtable, platform=3, encoding=1):
    cmap = struct.pack(">HH", 0, 1) + struct.pack(">HHI", platform, encoding, 12) + subtable
    offset = 12 + 16
    header = struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0)
    record = b"cmap" + struct.pack(">III", 0, offset, len(cmap))
    return header + record + cmap


def collection(data):
    shift = 16
    table_offset = struct.unpack(">I", data[12 + 8:12 + 12])[0] + shift
    data = data[:20] + struct.pack(">I", table_offset) + data[24:]
    return b"ttcf" + struct.pack(">HHI", 1, 0, 1) + struct.pack(">I", shift) + data


class FontCheckTest(unittest.TestCase):

    def test_latin_only(self):
        self.assertFalse(has_cyrillic(font(format4([(0x20, 0x7E, -29)]))))

    def test_cyrillic_format4(self):
        data = font(format4([(0x20, 0x7E, -29), (0x0410, 0x044F, -900)]))
        self.assertTrue(has_cyrillic(data))
        self.assertTrue(has_chars(data, [0x41]))
        self.assertFalse(has_chars(data, [0x0401]))

    def test_cyrillic_format12(self):
        self.assertTrue(has_cyrillic(font(format12([(0x20, 0x7E), (0x0400, 0x04FF)]), encoding=10)))

    def test_ignores_symbol_cmap(self):
        self.assertFalse(has_cyrillic(font(format4([(0x0400, 0x04FF, 10)]), encoding=0)))

    def test_collection(self):
        self.assertTrue(has_cyrillic(collection(font(format4([(0x0400, 0x04FF, 10)])))))

    def test_garbage(self):
        self.assertFalse(has_cyrillic(b"not a font"))
        self.assertFalse(has_cyrillic(b""))


if __name__ == "__main__":
    unittest.main()
