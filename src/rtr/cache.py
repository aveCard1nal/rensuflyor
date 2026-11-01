from __future__ import absolute_import, unicode_literals

import io
import json
import os
import threading


class Cache(object):

    def __init__(self, path=None):
        self.path = path
        self.entries = {}
        self.lock = threading.Lock()
        self.needs_newline = False

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return 0
        with io.open(self.path, "rb") as f:
            data = f.read()
        count = 0
        for raw in data.splitlines():
            try:
                src, dst = json.loads(raw.decode("utf-8"))
            except (ValueError, TypeError, UnicodeDecodeError):
                continue
            if dst is None:
                self.entries.pop(src, None)
            else:
                self.entries[src] = dst
            count += 1
        self.needs_newline = bool(data) and not data.endswith(b"\n")
        return len(self.entries)

    def get(self, text):
        return self.entries.get(text)

    def __contains__(self, text):
        return text in self.entries

    def __len__(self):
        return len(self.entries)

    def clear(self):
        with self.lock:
            self.entries = {}
            if self.path and os.path.exists(self.path):
                os.remove(self.path)

    def forget(self, texts):
        texts = [t for t in texts if t in self.entries]
        if not texts:
            return
        with self.lock:
            for t in texts:
                self.entries.pop(t, None)
            self._append([(t, None) for t in texts])

    def _append(self, pairs):
        if not self.path:
            return
        data = "".join(json.dumps([s, d], ensure_ascii=False) + "\n" for s, d in pairs)
        if not isinstance(data, bytes):
            data = data.encode("utf-8")
        if self.needs_newline:
            data = b"\n" + data
            self.needs_newline = False
        with io.open(self.path, "ab") as f:
            f.write(data)

    def put_many(self, pairs):
        pairs = [(s, d) for s, d in pairs if self.entries.get(s) != d]
        if not pairs:
            return
        with self.lock:
            for s, d in pairs:
                self.entries[s] = d
            self._append(pairs)
