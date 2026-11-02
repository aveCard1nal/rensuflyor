from __future__ import absolute_import, unicode_literals

import re

from rensuflyor.codec import CodecError, decode, encode
from rensuflyor.protect import compile_terms, protect
from rensuflyor.segment import split
from rensuflyor.tags import TEXT, Token, escape_text, tokenize

_SPACE_BEFORE_PUNCT = re.compile(r"(</span>|</x>|<x[^>]*/>)\s+(?=[.,!?;:…)])")
_SPACE_AFTER_OPEN_PAREN = re.compile(r"\(\s+(?=<)")


_ATOM = re.compile(r"<x\s+id\s*=\s*[\"']?(\d+)[\"']?\s*(?:/>|>\s*</x\s*>)", re.IGNORECASE)


def _atom_spacing(html):
    rv = {}
    for m in _ATOM.finditer(html):
        before = m.start() > 0 and html[m.start() - 1].isspace()
        after = m.end() < len(html) and html[m.end()].isspace()
        rv[m.group(1)] = (before, after)
    return rv


def _restore_atom_spacing(html, source):
    want = _atom_spacing(source)
    out = []
    pos = 0
    for m in _ATOM.finditer(html):
        spacing = want.get(m.group(1))
        out.append(html[pos:m.start()])
        if spacing is not None:
            text = "".join(out)
            if spacing[0] and text and not text[-1].isspace() and text[-1] not in "([{«\"'":
                out.append(" ")
            elif not spacing[0] and text.endswith(" ") and len(text) > 1 and not text[-2].isspace():
                out = [text[:-1]]
        out.append(m.group(0))
        pos = m.end()
        if spacing is not None and spacing[1] and pos < len(html) and html[pos].isalnum():
            out.append(" ")
    out.append(html[pos:])
    return "".join(out)


def tidy_html(html, source=None):
    html = _SPACE_BEFORE_PUNCT.sub(r"\1", html)
    html = _SPACE_AFTER_OPEN_PAREN.sub("(", html)
    if source is not None:
        html = _restore_atom_spacing(html, source)
    return html


def _same(html, source=None):
    return html


def _has_letters(s):
    return any(c.isalpha() for c in s)


def _first_letter(tokens):
    for t in tokens:
        if t.kind == TEXT:
            for c in t.text:
                if c.isalpha():
                    return c
    return None


def match_case(source_tokens, result, percent=False):
    first = _first_letter(source_tokens)
    if first is None or not first.isupper():
        return result
    out = []
    done = False
    for t in tokenize(result, percent):
        if not done and t.kind == TEXT:
            for i, c in enumerate(t.text):
                if c.isalpha():
                    if c.islower():
                        text = t.text[:i] + c.upper() + t.text[i + 1:]
                        t = Token(TEXT, escape_text(text, percent), text=text)
                    done = True
                    break
        out.append(t.raw)
    return "".join(out)


class Job(object):

    def __init__(self, segment, encoded):
        self.segment = segment
        self.encoded = encoded
        self.result = None


class Translator(object):

    def __init__(self, client, terms=(), percent=False):
        self.client = client
        self.percent = percent
        self.terms = set(terms)
        self.pattern = compile_terms(terms)
        self.stats = {"text": 0, "html": 0, "pieces": 0}

    def set_terms(self, terms):
        self.terms = set(terms)
        self.pattern = compile_terms(terms)

    def _unique(self, texts, fmt):
        unique = []
        seen = set()
        for t in texts:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        if not unique:
            return {}
        return dict(zip(unique, self.client.translate(unique, fmt)))

    def _try(self, jobs, fmt, prepare):
        done = self._unique([j.encoded.html for j in jobs], fmt)
        failed = []
        for j in jobs:
            try:
                result = decode(prepare(done[j.encoded.html] or "", j.encoded.html), j.encoded, self.percent)
            except CodecError:
                failed.append(j)
                continue
            if not _has_letters(result):
                failed.append(j)
                continue
            j.result = result
            self.stats[fmt] += 1
        return failed

    def _pieces(self, jobs):
        texts = []
        for j in jobs:
            for t in j.segment.tokens:
                if t.kind == TEXT and _has_letters(t.text):
                    texts.append(t.text.strip())
        done = self._unique(texts, "text")
        for j in jobs:
            out = []
            for t in j.segment.tokens:
                if t.kind == TEXT and _has_letters(t.text):
                    core = t.text.strip()
                    lead = t.text[:len(t.text) - len(t.text.lstrip())]
                    trail = t.text[len(t.text.rstrip()):]
                    out.append(lead + escape_text((done[core] or core).strip(), self.percent) + trail)
                else:
                    out.append(t.raw)
            j.result = "".join(out)
            self.stats["pieces"] += 1

    def translate(self, texts):
        lines = []
        jobs = []
        for text in texts:
            line = split(text, self.percent)
            line_jobs = []
            for seg in line.segments:
                protect(seg, self.pattern, self.percent)
                if seg.translatable:
                    line_jobs.append(Job(seg, encode(seg)))
            lines.append((line, line_jobs))
            jobs.extend(line_jobs)
        failed = jobs
        try:
            for fmt in getattr(self.client, "formats", ("text", "html")):
                if failed:
                    failed = self._try(failed, fmt, tidy_html if fmt == "html" else _same)
            if failed:
                self._pieces(failed)
        except Exception:
            if failed is jobs:
                raise
        out = []
        for line, line_jobs in lines:
            if any(j.result is None for j in line_jobs):
                out.append(None)
                continue
            for j in line_jobs:
                j.result = match_case(j.segment.tokens, j.result, self.percent)
            out.append(line.join(dict((id(j.segment), j.result) for j in line_jobs)))
        return out
