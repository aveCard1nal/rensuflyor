from __future__ import unicode_literals

import re

TEXT = "text"
TAG = "tag"
INTERP = "interp"
BREAK = "break"

SPLIT_TAGS = frozenset(["w", "p", "nw", "fast", "done", "clear"])

_PERCENT_INTERP = re.compile(r"%\([^)]*\)[-#0 +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z]")


class Token(object):
    __slots__ = ("kind", "raw", "text", "key", "closing")

    def __init__(self, kind, raw, text=None, key=None, closing=False):
        self.kind = kind
        self.raw = raw
        self.text = text
        self.key = key
        self.closing = closing

    def is_split(self):
        return self.kind == BREAK or (self.kind == TAG and not self.closing and self.key in SPLIT_TAGS)

    def __repr__(self):
        return "Token(%s, %r)" % (self.kind, self.raw)


def _tag_token(raw):
    inner = raw[1:-1]
    closing = inner.startswith("/")
    if closing:
        inner = inner[1:]
    if inner.startswith("=") or inner.startswith("#"):
        key = inner
    else:
        key = inner.split("=", 1)[0]
    return Token(TAG, raw, key=key, closing=closing)


def _find_interp_end(s, i):
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def tokenize(s, percent=False):
    tokens = []
    buf = []
    raw_buf = []

    def flush():
        if buf:
            tokens.append(Token(TEXT, "".join(raw_buf), text="".join(buf)))
            del buf[:]
            del raw_buf[:]

    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "{":
            if s.startswith("{{", i):
                buf.append("{")
                raw_buf.append("{{")
                i += 2
                continue
            j = s.find("}", i)
            if j < 0:
                buf.append(s[i:])
                raw_buf.append(s[i:])
                break
            flush()
            tokens.append(_tag_token(s[i:j + 1]))
            i = j + 1
        elif c == "[":
            if s.startswith("[[", i):
                buf.append("[")
                raw_buf.append("[[")
                i += 2
                continue
            j = _find_interp_end(s, i)
            if j < 0:
                buf.append(s[i:])
                raw_buf.append(s[i:])
                break
            flush()
            tokens.append(Token(INTERP, s[i:j + 1]))
            i = j + 1
        elif c == "%" and percent:
            if s.startswith("%%", i):
                buf.append("%")
                raw_buf.append("%%")
                i += 2
                continue
            m = _PERCENT_INTERP.match(s, i)
            if m:
                flush()
                tokens.append(Token(INTERP, m.group(0)))
                i = m.end()
                continue
            buf.append(c)
            raw_buf.append(c)
            i += 1
        elif c == "\n":
            flush()
            tokens.append(Token(BREAK, c))
            i += 1
        else:
            buf.append(c)
            raw_buf.append(c)
            i += 1
    flush()
    return tokens


def escape_text(s, percent=False):
    s = s.replace("{", "{{").replace("[", "[[")
    if percent:
        s = s.replace("%", "%%")
    return s
