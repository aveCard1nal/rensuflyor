from __future__ import absolute_import, unicode_literals

import re

from rensuflyor.tags import TEXT, Token, escape_text

TERM = "term"


def clean_terms(terms):
    out = set()
    for t in terms:
        if not t:
            continue
        t = t.strip()
        if not t or any(c in t for c in "{}[]%\n"):
            continue
        if not any(c.isalpha() for c in t):
            continue
        out.add(t)
    return sorted(out, key=lambda s: (-len(s), s))


def compile_terms(terms):
    terms = clean_terms(terms)
    if not terms:
        return None
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in terms) + r")(?!\w)", re.UNICODE)


def protect(segment, pattern, percent=False):
    if pattern is None:
        return segment
    tokens = []
    for t in segment.tokens:
        if t.kind != TEXT:
            tokens.append(t)
            continue
        pos = 0
        for m in pattern.finditer(t.text):
            if m.start() > pos:
                piece = t.text[pos:m.start()]
                tokens.append(Token(TEXT, escape_text(piece, percent), text=piece))
            tokens.append(Token(TERM, m.group(0)))
            pos = m.end()
        if pos == 0:
            tokens.append(t)
        elif pos < len(t.text):
            piece = t.text[pos:]
            tokens.append(Token(TEXT, escape_text(piece, percent), text=piece))
    segment.tokens = tokens
    return segment
