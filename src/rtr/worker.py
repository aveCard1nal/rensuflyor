from __future__ import unicode_literals

import threading
import time

from rtr import settings


class Worker(object):

    def __init__(self, translator, cache, log=None, clock=time.time, sleep=time.sleep):
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
        for source in (self.urgent, self.queue):
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
            if self.stopped:
                return False
            batch = self._take()
        ok = True
        try:
            results = self.translator.translate(batch)
            self.cache.put_many(zip(batch, results))
        except Exception as e:
            ok = False
            self.log("batch of %d failed: %s" % (len(batch), e))
        with self.cond:
            self.in_flight.difference_update(batch)
            if not ok:
                now = self.clock()
                for t in batch:
                    self.failed[t] = now
            self.cond.notify_all()
        if not ok:
            self.sleep(settings.error_pause)
        return True

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
