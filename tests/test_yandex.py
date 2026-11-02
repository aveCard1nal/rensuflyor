from __future__ import unicode_literals

import json
import unittest

from rensuflyor.client import TranslateError
from rensuflyor.yandex import YandexClient, parse_response

try:
    from urllib.parse import parse_qsl, urlparse
except ImportError:
    from urlparse import parse_qsl, urlparse


class Transport(object):

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, body, timeout):
        self.calls.append((url, body))
        return self.responses.pop(0)


def ok(texts):
    return 200, json.dumps({"code": 200, "lang": "en-ru", "text": texts}).encode("utf-8")


class YandexTest(unittest.TestCase):

    def test_request_shape(self):
        t = Transport([ok(["Привет", "Пока"])])
        c = YandexClient(ucid="abc", transport=t, sleep=lambda s: None)
        self.assertEqual(c.translate(["Hi", "Bye"], "html"), ["Привет", "Пока"])
        url, body = t.calls[0]
        query = dict(parse_qsl(urlparse(url).query))
        self.assertEqual(query, {"srv": "android", "ucid": "abc", "lang": "ru", "format": "html"})
        self.assertEqual(parse_qsl(body.decode("ascii")), [("text", "Hi"), ("text", "Bye")])

    def test_prefers_html(self):
        self.assertEqual(YandexClient.formats, ("html", "text"))

    def test_generates_ucid(self):
        self.assertEqual(len(YandexClient().ucid), 32)

    def test_error_code(self):
        data = json.dumps({"code": 413, "message": "too big"}).encode("utf-8")
        self.assertRaises(TranslateError, parse_response, data, 1)

    def test_count_mismatch(self):
        self.assertRaises(TranslateError, parse_response, ok(["a"])[1], 2)

    def test_retries_on_429(self):
        t = Transport([(429, b""), ok(["a"])])
        c = YandexClient(transport=t, sleep=lambda s: None)
        self.assertEqual(c.translate(["x"]), ["a"])


if __name__ == "__main__":
    unittest.main()
