from __future__ import unicode_literals

import json
import time

try:
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import urlencode
    from urllib2 import HTTPError, Request, URLError, urlopen

from rtr import settings

URL = "https://translate.googleapis.com/translate_a/t"
USER_AGENT = "Mozilla/5.0"


class TranslateError(Exception):
    pass


def http_transport(url, body, timeout):
    req = Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    })
    try:
        res = urlopen(req, timeout=timeout)
        try:
            return res.getcode(), res.read()
        finally:
            res.close()
    except HTTPError as e:
        return e.code, b""


def _utf8(s):
    return s.encode("utf-8")


def parse_response(data, count):
    res = json.loads(data.decode("utf-8"))
    if not isinstance(res, list):
        res = [res]
    out = []
    for item in res:
        while isinstance(item, list):
            item = item[0] if item else ""
        out.append(item)
    if len(out) != count:
        raise TranslateError("expected %d results, got %d" % (count, len(out)))
    return out


class GoogleClient(object):

    def __init__(self, transport=http_transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def _url(self, fmt):
        return URL + "?" + urlencode([
            ("client", "gtx"),
            ("sl", _utf8(settings.source_lang)),
            ("tl", _utf8(settings.target_lang)),
            ("format", _utf8(fmt)),
        ])

    def _request(self, texts, fmt):
        body = urlencode([("q", _utf8(t)) for t in texts])
        if not isinstance(body, bytes):
            body = body.encode("ascii")
        url = self._url(fmt)
        delay = 1.0
        error = None
        for attempt in range(settings.retries):
            if attempt:
                self.sleep(delay)
                delay *= 2
            try:
                status, data = self.transport(url, body, settings.timeout)
            except (URLError, IOError, OSError) as e:
                error = "network: %s" % (e,)
                continue
            if status == 200:
                return parse_response(data, len(texts))
            error = "http %d" % status
            if status not in (429, 500, 502, 503, 504):
                break
        raise TranslateError(error)

    def batches(self, texts):
        batch = []
        size = 0
        for t in texts:
            if batch and (len(batch) >= settings.batch_size or size + len(t) > settings.batch_chars):
                yield batch
                batch = []
                size = 0
            batch.append(t)
            size += len(t)
        if batch:
            yield batch

    def translate(self, texts, fmt="text"):
        out = []
        for batch in self.batches(texts):
            out.extend(self._request(batch, fmt))
        return out
