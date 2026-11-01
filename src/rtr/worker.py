from __future__ import absolute_import, unicode_literals

import threading
import time

from rtr import settings
from rtr.client import describe


class Worker(object):

    def __init__(self, translator, cache, log=None, clock=time.time, sleep=time.sleep, coalesce=None):
        self.coalesce = settings.coalesce if coalesce is None else coalesce
        self.translator = translator
        self.cache = cache
        self.log = log or (lambda message: None)
        self.clock = clock
        self.sleep = sleep
        self.cond = threading.Condition()
        self.urgent = []
        self.queue = []
        self.queued = set()
        self.in_flight = set()
        self.failed = {}
        self.stopped = False
        self.thread = None
        self.last_error = None
        self.healthy = True
        self.fail_streak = 0

    def _recently_failed(self, text):
        when = self.failed.get(text)
        return when is not None and self.clock() - when < settings.fail_cooldown

    def request(self, texts, urgent=False):
        added = False
        with self.cond:
            for t in texts:
                if not t or t in self.cache or t in self.in_flight or self._recently_failed(t):
                    continue
                if t in self.queued:
                    if urgent and t in self.queue:
                        self.queue.remove(t)
                        self.urgent.append(t)
                    continue
                self.queued.add(t)
                (self.urgent if urgent else self.queue).append(t)
                added = True
            if added:
                self.cond.notify_all()

    def wait(self, text, timeout):
        result = self.cache.get(text)
        if result is not None:
            return result
        self.request([text], urgent=True)
        if not self.healthy:
            return None
        deadline = self.clock() + timeout
        with self.cond:
            while True:
                result = self.cache.get(text)
                if result is not None:
                    return result
                if text not in self.queued and text not in self.in_flight:
                    return None
                remaining = deadline - self.clock()
                if remaining <= 0:
                    return None
                self.cond.wait(remaining)

    def _take(self):
        batch = []
        sources = (self.urgent,) if self.urgent else (self.queue,)
        for source in sources:
            while source and len(batch) < settings.batch_size:
                t = source.pop(0)
                self.queued.discard(t)
                batch.append(t)
        self.in_flight.update(batch)
        return batch

    def step(self):
        with self.cond:
            while not self.stopped and not self.urgent and not self.queue:
                self.cond.wait()
            if not self.stopped and not self.urgent and len(self.queue) < settings.batch_size and self.coalesce:
                self.cond.wait(self.coalesce)
            if self.stopped:
                return False
            batch = self._take()
        ok = True
        missing = []
        try:
            results = self.translator.translate(batch)
            self.cache.put_many([(t, r) for t, r in zip(batch, results) if r is not None])
            missing = [t for t, r in zip(batch, results) if r is None]
        except Exception as e:
            ok = False
            missing = batch
            self.last_error = describe(e)
            self.log("batch of %d failed: %s" % (len(batch), self.last_error))
        with self.cond:
            self.in_flight.difference_update(batch)
            self.healthy = ok
            now = self.clock()
            if ok:
                self.last_error = None
                self.fail_streak = 0
            else:
                self.fail_streak += 1
            for t in missing:
                self.failed[t] = now
            self.cond.notify_all()
        if not ok:
            self.sleep(min(settings.error_pause * 2 ** (self.fail_streak - 1), settings.max_error_pause))
        return True

    def reset_failures(self):
        with self.cond:
            self.failed = {}

    def run(self):
        while self.step():
            pass

    def start(self):
        self.thread = threading.Thread(target=self.run, name="rtr-worker")
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        with self.cond:
            self.stopped = True
            self.cond.notify_all()
