from __future__ import unicode_literals

import json
import unittest

from rensuflyor import settings
from rensuflyor.google import GoogleClient, TranslateError, parse_response

try:
    from urllib.parse import parse_qsl
except ImportError:
    from urlparse import parse_qsl


class FakeTransport(object):

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, body, timeout):
        self.calls.append((url, [v for k, v in parse_qsl(body.decode("ascii"))]))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def ok(items):
    return 200, json.dumps(items).encode("utf-8")


class ParseTest(unittest.TestCase):

    def test_plain_list(self):
        self.assertEqual(parse_response(ok(["а", "б"])[1], 2), ["а", "б"])

    def test_auto_pairs(self):
        self.assertEqual(parse_response(ok([["а", "en"], ["б", "en"]])[1], 2), ["а", "б"])

    def test_single_string(self):
        self.assertEqual(parse_response(ok("а")[1], 1), ["а"])

    def test_null_item_becomes_empty(self):
        self.assertEqual(parse_response(ok([["a", "en"], None])[1], 2), ["a", ""])

    def test_bad_item(self):
        self.assertRaises(TranslateError, parse_response, ok([1])[1], 1)

    def test_count_mismatch(self):
        self.assertRaises(TranslateError, parse_response, ok(["а"])[1], 2)


class ClientTest(unittest.TestCase):

    def setUp(self):
        self.sleeps = []

    def client(self, responses):
        self.transport = FakeTransport(responses)
        return GoogleClient(self.transport, self.sleeps.append)

    def test_sends_utf8_and_format(self):
        c = self.client([ok([["Привет", "en"]])])
        self.assertEqual(c.translate(["Hi — there"], "html"), ["Привет"])
        url, qs = self.transport.calls[0]
        self.assertIn("format=html", url)
        self.assertIn("tl=ru", url)
        self.assertEqual(qs, ["Hi — there"])

    def test_batches_by_count(self):
        old = settings.batch_size
        settings.batch_size = 2
        try:
            c = self.client([ok(["1", "2"]), ok(["3"])])
            self.assertEqual(c.translate(["a", "b", "c"]), ["1", "2", "3"])
            self.assertEqual(len(self.transport.calls), 2)
        finally:
            settings.batch_size = old

    def test_batches_by_chars(self):
        old = settings.batch_chars
        settings.batch_chars = 5
        try:
            c = self.client([ok(["1"]), ok(["2"])])
            self.assertEqual(c.translate(["aaaa", "bbbb"]), ["1", "2"])
        finally:
            settings.batch_chars = old

    def test_retries_rate_limit(self):
        c = self.client([(429, b""), (503, b""), ok(["ok"])])
        self.assertEqual(c.translate(["x"]), ["ok"])
        self.assertEqual(self.sleeps, [1.0, 2.0])

    def test_retries_network_error(self):
        c = self.client([IOError("reset"), ok(["ok"])])
        self.assertEqual(c.translate(["x"]), ["ok"])

    def test_gives_up(self):
        c = self.client([(429, b"")] * settings.retries)
        self.assertRaises(TranslateError, c.translate, ["x"])

    def test_retries_any_transport_error(self):
        c = self.client([ValueError("BadStatusLine"), ok(["ok"])])
        self.assertEqual(c.translate(["x"]), ["ok"])

    def test_retries_truncated_body(self):
        c = self.client([(200, b"[[\"a"), ok(["ok"])])
        self.assertEqual(c.translate(["x"]), ["ok"])

    def test_no_retry_on_client_error(self):
        c = self.client([(400, b"")])
        self.assertRaises(TranslateError, c.translate, ["x"])
        self.assertEqual(len(self.transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
