import io
import os
import re
import shutil
import sys
import tempfile
import types
import unittest

import build


class FakeLog(object):

    def __init__(self):
        self.lines = []

    def write(self, text, *args):
        self.lines.append(text % args)


class FakeCharacter(object):

    def __init__(self, name, dynamic=False):
        self.name = name
        self.dynamic = dynamic


class Namespace(object):

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakePersistent(object):

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return None


class FakeTranslator(object):

    def __init__(self, fn):
        self.fn = fn
        self.terms = None

    def translate(self, texts):
        return [self.fn(t) for t in texts]

    def set_terms(self, terms):
        self.terms = terms


class FakeFontGroup(object):

    def __init__(self):
        self.added = []

    def add(self, font, start, end):
        self.added.append((font, start, end))
        return self


class FakeFile(object):

    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def close(self):
        pass


def fake_load(name):
    if name == "cyr.ttf":
        from tests.test_fontcheck import font, format4
        return FakeFile(font(format4([(0x0400, 0x04FF, 10)])))
    if name == "latin.ttf":
        return FakeFile(b"latin")
    raise IOError(name)


def make_fake_renpy(gamedir):
    renpy = types.ModuleType("renpy")
    renpy.config = Namespace(
        say_menu_text_filter=None,
        old_substitutions=True,
        gamedir=gamedir,
        savedir=None,
        keymap={},
        underlay=[],
        font_transforms={},
    )
    renpy.display = types.ModuleType("renpy.display")
    renpy.display.log = FakeLog()
    renpy.display.behavior = Namespace(Keymap=lambda **kw: ("keymap", kw))
    renpy.display.predict = Namespace(predicting=False)
    renpy.character = Namespace(ADVCharacter=FakeCharacter)
    renpy.store = types.ModuleType("store")
    renpy.store.e = FakeCharacter("Eileen")
    renpy.store.n = FakeCharacter("[player]")
    renpy.store.mc = FakeCharacter("name", dynamic=True)
    renpy.store.ToggleScreen = lambda name: ("toggle", name)
    renpy.game = Namespace(persistent=FakePersistent(), preferences=Namespace(font_transform=None))
    renpy.exports = Namespace(save_persistent=lambda: None)
    renpy.text = Namespace(font=Namespace(FontGroup=FakeFontGroup))
    renpy.loader = Namespace(load=fake_load)
    return renpy


def python_blocks(text):
    blocks = []
    current = None
    for line in text.splitlines():
        m = re.match(r"init (-?\d+) python", line)
        if m:
            current = []
            blocks.append((int(m.group(1)), current))
        elif line and not line.startswith(" "):
            current = None
        elif current is not None:
            current.append(line[4:] if line.startswith("    ") else line)
    blocks.sort(key=lambda b: b[0])
    return ["\n".join(b) + "\n" for _, b in blocks]


class BuildTest(unittest.TestCase):

    def setUp(self):
        self.saved = dict(sys.modules)
        for name in list(sys.modules):
            if name == "rtr" or name.startswith("rtr."):
                del sys.modules[name]
        self.dir = tempfile.mkdtemp()
        self.renpy = make_fake_renpy(self.dir)
        sys.modules["renpy"] = self.renpy

    def tearDown(self):
        worker = getattr(sys, "_rtr_worker", None)
        if worker is not None:
            worker.stop()
            del sys._rtr_worker
        sys.modules.clear()
        sys.modules.update(self.saved)
        shutil.rmtree(self.dir)

    def run_built(self):
        path = build.build()
        with io.open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("init -998 python hide:\n    import rtr.settings as s\n"))
        self.assertIn("screen rtr_settings():", text)
        for block in python_blocks(text):
            exec(compile(block, path, "exec"), {})
        return sys.modules["rtr.hooks"]

    def test_installs_filter_and_key(self):
        hooks = self.run_built()
        hooks._worker.translator = FakeTranslator(lambda t: "T:" + t)
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "T:Hello")
        self.assertEqual(self.renpy.config.say_menu_text_filter("..."), "...")
        self.assertEqual(self.renpy.config.keymap["rtr_settings"], ["K_F8"])
        self.assertEqual(self.renpy.config.underlay, [("keymap", {"rtr_settings": ("toggle", "rtr_settings")})])

    def test_font_fallback(self):
        hooks = self.run_built()
        self.assertEqual(self.renpy.game.preferences.font_transform, "rtr_cyrillic")
        transform = self.renpy.config.font_transforms["rtr_cyrillic"]
        self.assertEqual(transform("cyr.ttf"), "cyr.ttf")
        group = transform("latin.ttf")
        self.assertEqual(group.added[0], ("DejaVuSans.ttf", 0x0400, 0x052F))
        self.assertEqual(group.added[-1], ("latin.ttf", None, None))
        self.assertIs(transform("latin.ttf"), group)
        self.assertIsInstance(transform("missing.ttf"), FakeFontGroup)

    def test_font_single_mode(self):
        hooks = self.run_built()
        transform = self.renpy.config.font_transforms["rtr_cyrillic"]
        self.assertIsInstance(transform("latin.ttf"), FakeFontGroup)
        hooks.toggle_font_single()
        self.assertTrue(hooks.status()["font_single"])
        self.assertEqual(transform("latin.ttf"), "DejaVuSans.ttf")
        self.assertEqual(transform("cyr.ttf"), "cyr.ttf")
        hooks.toggle_font_single()
        self.assertIsInstance(transform("latin.ttf"), FakeFontGroup)

    def test_font_fallback_keeps_user_choice(self):
        self.renpy.game.preferences.font_transform = "opendyslexic"
        self.run_built()
        self.assertEqual(self.renpy.game.preferences.font_transform, "opendyslexic")

    def test_prediction_never_waits(self):
        hooks = self.run_built()
        calls = []
        hooks._worker.wait = lambda text, timeout: calls.append(text)
        self.renpy.display.predict.predicting = True
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "Hello")
        self.assertEqual(calls, [])
        hooks._cache.put_many([("Hello", "Привет")])
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "Привет")

    def test_error_is_escaped(self):
        hooks = self.run_built()
        hooks._worker.last_error = "network: {x} [Errno 11001]"
        self.assertEqual(hooks.status()["error"], "network: {{x} [Errno 11001]")

    def test_chains_previous_filter(self):
        self.renpy.config.say_menu_text_filter = lambda s: s + "!"
        hooks = self.run_built()
        hooks._worker.translator = FakeTranslator(lambda t: t)
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hi"), "Hi!")

    def test_disable_translation(self):
        hooks = self.run_built()
        hooks._worker.translator = FakeTranslator(lambda t: "T:" + t)
        hooks.toggle_enabled()
        self.assertFalse(hooks.status()["enabled"])
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "Hello")
        hooks.toggle_enabled()
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "T:Hello")

    def test_show_both(self):
        hooks = self.run_built()
        hooks._worker.translator = FakeTranslator(lambda t: "T:" + t)
        hooks.toggle_both()
        out = self.renpy.config.say_menu_text_filter("Hello{nw}")
        self.assertTrue(out.startswith("T:Hello\n{size=-6}"))
        self.assertTrue(out.endswith("Hello{/alpha}{/size}{nw}"))
        self.assertEqual(hooks._cache.get("Hello{nw}"), "T:Hello{nw}")

    def test_reinstall_stops_old_worker(self):
        self.run_built()
        first = sys._rtr_worker
        for name in list(sys.modules):
            if name == "rtr" or name.startswith("rtr."):
                del sys.modules[name]
        self.run_built()
        first.thread.join(5)
        self.assertFalse(first.thread.is_alive())
        self.assertIsNot(sys._rtr_worker, first)

    def test_names_protected_by_default(self):
        hooks = self.run_built()
        self.assertEqual(hooks.collect_terms(), set(["Eileen"]))

    def test_toggle_names(self):
        hooks = self.run_built()
        hooks._worker.translator = FakeTranslator(lambda t: t)
        hooks.toggle_names()
        self.assertTrue(self.renpy.game.persistent._rtr_translate_names)
        self.assertEqual(hooks._worker.translator.terms, set())

    def test_glossary(self):
        hooks = self.run_built()
        with io.open(os.path.join(self.dir, "rtr_glossary.txt"), "wb") as f:
            f.write(u"﻿WIZ\r\nKNIGHT\n\n".encode("utf-8"))
        self.assertEqual(hooks.collect_terms(), set(["WIZ", "KNIGHT", "Eileen", ""]))

    def test_provider_switch_uses_own_cache(self):
        hooks = self.run_built()
        self.assertEqual(os.path.basename(hooks._cache.path), "rtr_cache_ru_google.jsonl")
        first = hooks._worker
        hooks.set_provider("yandex")
        self.assertEqual(self.renpy.game.persistent._rtr_provider, "yandex")
        self.assertEqual(os.path.basename(hooks._cache.path), "rtr_cache_ru_yandex.jsonl")
        self.assertIsNot(hooks._worker, first)
        self.assertEqual(hooks._worker.translator.client.ucid, self.renpy.game.persistent._rtr_ucid)
        hooks.set_provider("bogus")
        self.assertEqual(hooks.provider(), "yandex")

    def test_clear_cache(self):
        hooks = self.run_built()
        hooks._cache.put_many([("a", "b")])
        self.assertTrue(os.path.exists(hooks._cache.path))
        hooks.clear_cache()
        self.assertEqual(hooks.status()["cached"], 0)
        self.assertFalse(os.path.exists(hooks._cache.path))


if __name__ == "__main__":
    unittest.main()
