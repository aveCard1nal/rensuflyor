from __future__ import unicode_literals

from rtr.tags import TAG, tokenize

ORIGINAL_OPEN = "{size=-6}{alpha=*0.75}"
ORIGINAL_CLOSE = "{/alpha}{/size}"


def _is_control(token):
    return token.is_split() and token.kind == TAG


def strip_control(text, percent=False):
    return "".join(t.raw for t in tokenize(text, percent) if not _is_control(t))


def combine(translated, original, percent=False, inline=False):
    if translated == original:
        return translated
    tokens = tokenize(translated, percent)
    tail = []
    while tokens and tokens[-1].kind == TAG and not tokens[-1].closing and tokens[-1].key == "nw":
        tail.insert(0, tokens.pop())
    head = "".join(t.raw for t in tokens).rstrip()
    body = strip_control(original, percent).strip()
    separator = " / " if inline else "\n"
    return head + separator + ORIGINAL_OPEN + body + ORIGINAL_CLOSE + "".join(t.raw for t in tail)
