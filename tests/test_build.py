import io
import re
import sys
import types
import unittest

import build


class FakeLog(object):

    def __init__(self):
        self.lines = []

    def write(self, text, *args):
        self.lines.append(text % args)


class FakeCharacter(object):

    def __init__(self, name):
        self.name = name


class Namespace(object):
    pass


def make_fake_renpy():
    renpy = types.ModuleType("renpy")
    renpy.config = Namespace()
    renpy.config.say_menu_text_filter = None
    renpy.config.old_substitutions = True
    renpy.display = types.ModuleType("renpy.display")
    renpy.display.log = FakeLog()
    renpy.character = Namespace()
    renpy.character.ADVCharacter = FakeCharacter
    renpy.store = types.ModuleType("store")
    renpy.store.e = FakeCharacter("Eileen")
    renpy.store.n = FakeCharacter("[player]")
    renpy.loader = Namespace()
    renpy.loader.loadable = lambda name: False
    return renpy


def python_blocks(text):
    blocks = []
    current = None
    for line in text.splitlines():
        m = re.match(r"init (-?\d+) python", line)
        if m:
            current = []
            blocks.append((int(m.group(1)), current))
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
        self.renpy = make_fake_renpy()
        sys.modules["renpy"] = self.renpy

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved)

    def run_built(self):
        path = build.build()
        with io.open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("init -998 python hide:\n    import rtr.settings as s\n"))
        for block in python_blocks(text):
            exec(compile(block, path, "exec"), {})
        return sys.modules["rtr.hooks"]

    def test_installs_filter(self):
        hooks = self.run_built()
        hooks._translator.translate = lambda texts: ["T:" + t for t in texts]
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "T:Hello")
        self.assertTrue(any("installed" in line for line in self.renpy.display.log.lines))

    def test_chains_previous_filter(self):
        self.renpy.config.say_menu_text_filter = lambda s: s + "!"
        hooks = self.run_built()
        hooks._translator.translate = lambda texts: texts
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hi"), "Hi!")

    def test_names_protected_by_default(self):
        hooks = self.run_built()
        self.assertEqual(hooks.collect_terms(), set(["Eileen"]))

    def test_names_translated_when_enabled(self):
        hooks = self.run_built()
        sys.modules["rtr.settings"].translate_names = True
        self.assertEqual(hooks.collect_terms(), set())


if __name__ == "__main__":
    unittest.main()
