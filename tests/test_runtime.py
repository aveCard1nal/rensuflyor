from __future__ import unicode_literals

import io
import os
import shutil
import tempfile
import threading
import unittest

from rtr import settings
from rtr.cache import Cache
from rtr.lookahead import collect
from rtr.worker import Worker


class CacheTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "c.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_roundtrip(self):
        c = Cache(self.path)
        c.put_many([("Hi {b}there{/b}", "Привет {b}там{/b}"), ("a\nb", "а\nб")])
        c.put_many([("Hi {b}there{/b}", "Привет {b}там{/b}")])
        d = Cache(self.path)
        self.assertEqual(d.load(), 2)
        self.assertEqual(d.get("a\nb"), "а\nб")
        self.assertIn("Hi {b}there{/b}", d)

    def test_later_entry_wins_and_garbage_skipped(self):
        c = Cache(self.path)
        c.put_many([("x", "1")])
        c.put_many([("x", "2")])
        with io.open(self.path, "ab") as f:
            f.write(b"[\"broken\n")
        d = Cache(self.path)
        d.load()
        self.assertEqual(d.get("x"), "2")
        self.assertEqual(len(d), 1)

    def test_memory_only(self):
        c = Cache(None)
        self.assertEqual(c.load(), 0)
        c.put_many([("x", "1")])
        self.assertEqual(c.get("x"), "1")


class FakeTranslator(object):

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def translate(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise IOError("down")
        return ["RU:" + t for t in texts]


class Clock(object):

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class WorkerTest(unittest.TestCase):

    def make(self, fail=False):
        self.clock = Clock()
        self.translator = FakeTranslator(fail)
        self.cache = Cache(None)
        self.sleeps = []
        return Worker(self.translator, self.cache, clock=self.clock, sleep=self.sleeps.append)

    def test_urgent_goes_first(self):
        w = self.make()
        w.request(["a", "b", "c"])
        w.request(["c", "z"], urgent=True)
        old = settings.batch_size
        settings.batch_size = 2
        try:
            w.step()
        finally:
            settings.batch_size = old
        self.assertEqual(self.translator.calls[0], ["c", "z"])
        self.assertEqual(self.cache.get("z"), "RU:z")

    def test_skips_cached_and_duplicates(self):
        w = self.make()
        self.cache.put_many([("a", "A")])
        w.request(["a", "b", "b"])
        w.step()
        self.assertEqual(self.translator.calls, [["b"]])

    def test_failure_cooldown(self):
        w = self.make(fail=True)
        w.request(["a"])
        w.step()
        self.assertEqual(self.sleeps, [settings.error_pause])
        w.request(["a"])
        self.assertEqual(w.queue, [])
        self.clock.now += settings.fail_cooldown + 1
        w.request(["a"])
        self.assertEqual(w.queue, ["a"])

    def test_wait_returns_cached(self):
        w = self.make()
        self.cache.put_many([("a", "A")])
        self.assertEqual(w.wait("a", 0), "A")

    def test_wait_times_out(self):
        w = self.make()
        self.assertIsNone(w.wait("a", 0))
        self.assertEqual(w.urgent, ["a"])

    def test_wait_with_thread(self):
        w = Worker(FakeTranslator(), Cache(None))
        w.start()
        try:
            self.assertEqual(w.wait("hello", 5), "RU:hello")
        finally:
            w.stop()
            w.thread.join(5)
        self.assertFalse(w.thread.is_alive())

    def test_wait_gives_up_after_failure(self):
        w = Worker(FakeTranslator(fail=True), Cache(None), sleep=lambda s: None)
        w.start()
        try:
            self.assertIsNone(w.wait("hello", 5))
        finally:
            w.stop()
            w.thread.join(5)


class Node(object):

    def __init__(self, **kw):
        self.next = None
        self.__dict__.update(kw)


def node(kind, **kw):
    return type(str(kind), (Node,), {})(**kw)


def chain(*nodes):
    for a, b in zip(nodes, nodes[1:]):
        a.next = b
    return nodes[0]


class LookaheadTest(unittest.TestCase):

    def test_linear(self):
        start = chain(node("Say", what="0"), node("Say", what="1"), node("Scene"), node("Say", what="2"))
        self.assertEqual(collect(start, None, 10), ["1", "2"])

    def test_limit(self):
        start = chain(*[node("Say", what=str(i)) for i in range(10)])
        self.assertEqual(collect(start, None, 3), ["1", "2", "3"])

    def test_menu_branches_breadth_first(self):
        after = node("Say", what="after")
        a = chain(node("Say", what="a1"), node("Say", what="a2"), after)
        b = chain(node("Say", what="b1"), after)
        menu = node("Menu", items=[("Choice A", None, [a]), ("Choice B", None, [b]), ("caption", None, None)])
        start = chain(node("Say", what="q"), menu)
        self.assertEqual(collect(start, None, 10), ["Choice A", "Choice B", "caption", "a1", "b1", "a2", "after"])

    def test_if_and_jump(self):
        labels = {"target": chain(node("Label"), node("Say", what="jumped"))}
        yes = [node("Say", what="yes")]
        no = [node("Jump", target="target", expression=False)]
        start = node("Say", what="s", next=node("If", entries=[("c", yes), ("True", no)]))
        self.assertEqual(collect(start, labels.get, 10), ["yes", "jumped"])

    def test_call_and_bad_lookup(self):
        def lookup(name):
            raise KeyError(name)
        start = chain(node("Say", what="s"), node("Call", label="nope", expression=False), node("Say", what="back"))
        self.assertEqual(collect(start, lookup, 10), ["back"])

    def test_dynamic_jump_ignored(self):
        start = chain(node("Say", what="s"), node("Jump", target="x + y", expression=True))
        self.assertEqual(collect(start, None, 10), [])

    def test_loop_terminates(self):
        a = node("Say", what="a")
        b = node("Say", what="b", next=a)
        a.next = b
        self.assertEqual(collect(a, None, 10), ["b"])


if __name__ == "__main__":
    unittest.main()
