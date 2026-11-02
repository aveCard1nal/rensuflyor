from __future__ import absolute_import, unicode_literals

from rensuflyor.tags import TEXT, Token, tokenize


class Segment(object):

    def __init__(self, tokens):
        self.lead = ""
        self.trail = ""
        tokens = list(tokens)
        if tokens and tokens[0].kind == TEXT:
            tokens[0] = _strip_token(tokens[0], left=True, segment=self)
        if tokens and tokens[-1].kind == TEXT:
            tokens[-1] = _strip_token(tokens[-1], left=False, segment=self)
        self.tokens = [t for t in tokens if not (t.kind == TEXT and not t.text)]

    @property
    def raw(self):
        return "".join(t.raw for t in self.tokens)

    @property
    def translatable(self):
        for t in self.tokens:
            if t.kind == TEXT and any(c.isalpha() for c in t.text):
                return True
        return False


def _strip_token(token, left, segment):
    text = token.text
    raw = token.raw
    if left:
        stripped = text.lstrip()
        ws = text[:len(text) - len(stripped)]
        segment.lead = ws
        return Token(TEXT, raw[len(ws):], text=stripped)
    stripped = text.rstrip()
    ws = text[len(stripped):]
    segment.trail = ws
    return Token(TEXT, raw[:len(raw) - len(ws)], text=stripped)


class Line(object):

    def __init__(self, parts):
        self.parts = parts

    @property
    def segments(self):
        return [p for p in self.parts if isinstance(p, Segment) and p.translatable]

    def join(self, translated):
        out = []
        for p in self.parts:
            if isinstance(p, Segment):
                body = translated.get(id(p), p.raw) if p.translatable else p.raw
                out.append(p.lead + body + p.trail)
            else:
                out.append(p)
        return "".join(out)


def split(text, percent=False):
    parts = []
    current = []
    for t in tokenize(text, percent):
        if t.is_split():
            parts.append(Segment(current))
            parts.append(t.raw)
            current = []
        else:
            current.append(t)
    parts.append(Segment(current))
    return Line(parts)
