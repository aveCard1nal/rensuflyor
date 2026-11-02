from __future__ import absolute_import, unicode_literals

import json

from rensuflyor import settings
from rensuflyor.client import Client, TranslateError, form, urlencode, utf8

URL = "https://translate.googleapis.com/translate_a/t"


def parse_response(data, count):
    res = json.loads(data.decode("utf-8"))
    if not isinstance(res, list):
        res = [res]
    out = []
    for item in res:
        while isinstance(item, list):
            item = item[0] if item else ""
        if item is None:
            item = ""
        if not isinstance(item, ("".__class__, b"".__class__)):
            raise TranslateError("unexpected item %r" % (item,))
        out.append(item)
    if len(out) != count:
        raise TranslateError("expected %d results, got %d" % (count, len(out)))
    return out


class GoogleClient(Client):

    name = "google"
    formats = ("text", "html")

    def url(self, fmt):
        return URL + "?" + urlencode([
            ("client", "gtx"),
            ("sl", utf8(settings.source_lang)),
            ("tl", utf8(settings.target_lang)),
            ("format", utf8(fmt)),
        ])

    def body(self, texts):
        return form([("q", t) for t in texts])

    def parse(self, data, count):
        return parse_response(data, count)
