from __future__ import absolute_import, unicode_literals

from collections import deque


def _first(block):
    if block:
        return block[0]
    return None


KINDS = ("Say", "Menu", "If", "While", "Jump", "Call")


def kind_of(node):
    for cls in type(node).__mro__:
        if cls.__name__ in KINDS:
            return cls.__name__
    return type(node).__name__


def successors(node, lookup):
    kind = kind_of(node)
    out = [getattr(node, "next", None)]
    if kind == "Menu":
        for item in node.items:
            out.append(_first(item[2]))
    elif kind == "If":
        for entry in node.entries:
            out.append(_first(entry[1]))
    elif kind == "While":
        out.append(_first(node.block))
    elif kind == "Jump":
        if not node.expression:
            out.append(lookup(node.target))
    elif kind == "Call":
        if not node.expression:
            out.append(lookup(node.label))
    return [n for n in out if n is not None]


def texts_of(node):
    kind = kind_of(node)
    if kind == "Say":
        if node.what:
            return [node.what]
    elif kind == "Menu":
        return [item[0] for item in node.items if item[0]]
    return []


def collect(start, lookup, limit, max_visits=None):
    if max_visits is None:
        max_visits = limit * 20

    def safe_lookup(name):
        try:
            return lookup(name)
        except Exception:
            return None

    out = []
    seen = set([id(start)])
    queue = deque(successors(start, safe_lookup))
    visits = 0
    while queue and len(out) < limit and visits < max_visits:
        node = queue.popleft()
        if id(node) in seen:
            continue
        seen.add(id(node))
        visits += 1
        out.extend(texts_of(node))
        queue.extend(successors(node, safe_lookup))
    return out[:limit]
