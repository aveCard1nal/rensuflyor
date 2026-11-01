from __future__ import unicode_literals

import re

from rtr.codec import CodecError, decode, encode
from rtr.protect import compile_terms, protect
from rtr.segment import split
from rtr.tags import TEXT, escape_text

_SPACE_BEFORE_PUNCT = re.compile(r"(</span>|</x>|<x[^>]*/>)\s+(?=[.,!?;:…)])")
_GLUED_AFTER_PUNCT = re.compile(r"([,.!?;:])(?=<x\b)")
_SPACE_AFTER_OPEN_PAREN = re.compile(r"\(\s+(?=<)")


def tidy_html(html):
    html = _SPACE_BEFORE_PUNCT.sub(r"\1", html)
    html = _GLUED_AFTER_PUNCT.sub(r"\1 ", html)
    html = _SPACE_AFTER_OPEN_PAREN.sub("(", html)
    return html


def _has_letters(s):
    return any(c.isalpha() for c in s)


class Job(object):

    def __init__(self, segment, encoded):
        self.segment = segment
        self.encoded = encoded
        self.result = None


class Translator(object):

    def __init__(self, client, terms=(), percent=False):
        self.client = client
        self.percent = percent
        self.pattern = compile_terms(terms)
        self.stats = {"text": 0, "html": 0, "pieces": 0}

    def set_terms(self, terms):
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
                j.result = decode(prepare(done[j.encoded.html]), j.encoded, self.percent)
                self.stats[fmt] += 1
            except CodecError:
                failed.append(j)
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
                    out.append(lead + escape_text(done[core].strip(), self.percent) + trail)
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
        failed = self._try(jobs, "text", lambda h: h)
        if failed:
            failed = self._try(failed, "html", tidy_html)
        if failed:
            self._pieces(failed)
        out = []
        for line, line_jobs in lines:
            out.append(line.join(dict((id(j.segment), j.result) for j in line_jobs)))
        return out
