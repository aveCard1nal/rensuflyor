from __future__ import absolute_import, unicode_literals

import json
import uuid

from rtr import settings
from rtr.client import Client, TranslateError, form, urlencode, utf8

URL = "https://translate.yandex.net/api/v1/tr.json/translate"


def new_ucid():
    return uuid.uuid4().hex


def lang_pair():
    if settings.source_lang and settings.source_lang != "auto":
        return "%s-%s" % (settings.source_lang, settings.target_lang)
    return settings.target_lang


def parse_response(data, count):
    res = json.loads(data.decode("utf-8"))
    if not isinstance(res, dict) or res.get("code") != 200:
        raise TranslateError("yandex code %s" % (res.get("code") if isinstance(res, dict) else res,))
    out = res.get("text")
    if not isinstance(out, list) or len(out) != count:
        raise TranslateError("expected %d results, got %r" % (count, out))
    return out


class YandexClient(Client):

    name = "yandex"
    formats = ("html", "text")

    def __init__(self, ucid=None, **kw):
        Client.__init__(self, **kw)
        self.ucid = ucid or new_ucid()

    def url(self, fmt):
        return URL + "?" + urlencode([
            ("srv", "android"),
            ("ucid", utf8(self.ucid)),
            ("lang", utf8(lang_pair())),
            ("format", utf8(fmt)),
        ])

    def body(self, texts):
        return form([("text", t) for t in texts])

    def parse(self, data, count):
        return parse_response(data, count)
