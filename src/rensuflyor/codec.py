from __future__ import absolute_import, unicode_literals

import re
import sys

from rensuflyor.tags import TAG, TEXT, escape_text

if sys.version_info[0] == 2:
    def _chr(code):
        if code > 0xFFFF:
            code -= 0x10000
            return unichr(0xD800 + (code >> 10)) + unichr(0xDC00 + (code & 0x3FF))
        return unichr(code)
else:
    _chr = chr

_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": " "}

_ENTITY = re.compile(r"&(#[xX][0-9a-fA-F]+|#\d+|[a-zA-Z]+);")

_MARKUP = re.compile(
    r"<\s*(/?)\s*(span|x)\b([^>]*?)(/?)\s*>",
    re.IGNORECASE,
)

_ID = re.compile(r"id\s*=\s*[\"']?(\d+)", re.IGNORECASE)


class CodecError(Exception):
    pass


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html_unescape(s):
    def sub(m):
        name = m.group(1)
        if name[0] == "#":
            try:
                if name[1] in "xX":
                    return _chr(int(name[2:], 16))
                return _chr(int(name[1:]))
            except (ValueError, OverflowError):
                return m.group(0)
        return _ENTITIES.get(name.lower(), m.group(0))
    return _ENTITY.sub(sub, s)


class Encoded(object):

    def __init__(self, html, opens, closes, atoms):
        self.html = html
        self.opens = opens
        self.closes = closes
        self.atoms = atoms


def _closed_later(tokens):
    rv = [False] * len(tokens)
    seen = set()
    for i in range(len(tokens) - 1, -1, -1):
        t = tokens[i]
        if t.kind != TAG:
            continue
        if t.closing:
            seen.add(t.key)
        else:
            rv[i] = t.key in seen
    return rv


def _pair(tokens):
    pairs = {}
    stack = []
    closable = _closed_later(tokens)
    for i, t in enumerate(tokens):
        if t.kind != TAG:
            continue
        if not t.closing:
            if closable[i]:
                stack.append(i)
        elif stack and tokens[stack[-1]].key == t.key:
            pairs[stack.pop()] = i
    return pairs


def encode(segment):
    tokens = segment.tokens
    pairs = _pair(tokens)
    closers = dict((c, o) for o, c in pairs.items())
    out = []
    opens = {}
    closes = {}
    atoms = {}
    ids = {}
    n = 0
    for i, t in enumerate(tokens):
        if t.kind == TEXT:
            out.append(html_escape(t.text))
        elif i in pairs:
            n += 1
            ids[i] = n
            opens[n] = t.raw
            out.append("<span id=\"%d\">" % n)
        elif i in closers:
            closes[ids[closers[i]]] = t.raw
            out.append("</span>")
        else:
            n += 1
            atoms[n] = t.raw
            out.append("<x id=\"%d\"></x>" % n)
    return Encoded("".join(out), opens, closes, atoms)


def decode(html, encoded, percent=False):
    out = []
    stack = []
    used = set()
    pos = 0
    for m in _MARKUP.finditer(html):
        out.append(escape_text(html_unescape(html[pos:m.start()]), percent))
        pos = m.end()
        closing, name, attrs, selfclose = m.groups()
        name = name.lower()
        if closing:
            if name == "x":
                continue
            if not stack:
                raise CodecError("unbalanced close")
            out.append(encoded.closes[stack.pop()])
            continue
        idm = _ID.search(attrs)
        if not idm:
            raise CodecError("markup without id")
        n = int(idm.group(1))
        if n in used:
            raise CodecError("duplicate id %d" % n)
        used.add(n)
        if name == "x":
            if n not in encoded.atoms:
                raise CodecError("unknown atom %d" % n)
            out.append(encoded.atoms[n])
        else:
            if n not in encoded.opens:
                raise CodecError("unknown span %d" % n)
            out.append(encoded.opens[n])
            if selfclose:
                out.append(encoded.closes[n])
            else:
                stack.append(n)
    out.append(escape_text(html_unescape(html[pos:]), percent))
    if stack:
        raise CodecError("unclosed span")
    expected = set(encoded.opens) | set(encoded.atoms)
    if used != expected:
        raise CodecError("missing ids %s" % sorted(expected - used))
    return "".join(out)
