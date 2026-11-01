from __future__ import unicode_literals

import os
import time

try:
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import urlencode
    from urllib2 import HTTPError, Request, URLError, urlopen

from rtr import settings

USER_AGENT = "Mozilla/5.0"
RETRY_STATUSES = (429, 500, 502, 503, 504)


class TranslateError(Exception):
    pass


_context = []


def ssl_context():
    if not _context:
        ctx = None
        try:
            import certifi
            import ssl
            path = certifi.where()
            if os.path.exists(path):
                ctx = ssl.create_default_context(cafile=path)
        except Exception:
            ctx = None
        _context.append(ctx)
    return _context[0]


def http_transport(url, body, timeout):
    req = Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    })
    try:
        ctx = ssl_context()
        if ctx is not None:
            res = urlopen(req, timeout=timeout, context=ctx)
        else:
            res = urlopen(req, timeout=timeout)
        try:
            return res.getcode(), res.read()
        finally:
            res.close()
    except HTTPError as e:
        return e.code, b""


def utf8(s):
    return s.encode("utf-8")


def form(pairs):
    body = urlencode([(utf8(k), utf8(v)) for k, v in pairs])
    if not isinstance(body, bytes):
        body = body.encode("ascii")
    return body


class Client(object):

    name = None

    def __init__(self, transport=http_transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def url(self, fmt):
        raise NotImplementedError

    def body(self, texts):
        raise NotImplementedError

    def parse(self, data, count):
        raise NotImplementedError

    def _request(self, texts, fmt):
        url = self.url(fmt)
        body = self.body(texts)
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
                return self.parse(data, len(texts))
            error = "http %d" % status
            if status not in RETRY_STATUSES:
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
