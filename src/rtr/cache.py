from __future__ import unicode_literals

import io
import json
import os
import threading


class Cache(object):

    def __init__(self, path=None):
        self.path = path
        self.entries = {}
        self.lock = threading.Lock()

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
            self.entries[src] = dst
            count += 1
        return count

    def get(self, text):
        return self.entries.get(text)

    def __contains__(self, text):
        return text in self.entries

    def __len__(self):
        return len(self.entries)

    def put_many(self, pairs):
        pairs = [(s, d) for s, d in pairs if self.entries.get(s) != d]
        if not pairs:
            return
        with self.lock:
            for s, d in pairs:
                self.entries[s] = d
            if self.path:
                lines = [json.dumps([s, d]) + "\n" for s, d in pairs]
                with io.open(self.path, "ab") as f:
                    f.write("".join(lines).encode("ascii"))
