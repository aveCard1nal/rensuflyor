import io
import sys
import types
import unittest

import build


class FakeLog(object):

    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)


def make_fake_renpy():
    renpy = types.ModuleType("renpy")
    renpy.config = types.SimpleNamespace() if hasattr(types, "SimpleNamespace") else type("Config", (), {})()
    renpy.config.say_menu_text_filter = None
    renpy.display = types.ModuleType("renpy.display")
    renpy.display.log = FakeLog()
    return renpy


def python_blocks(text):
    blocks = []
    current = None
    for line in text.splitlines():
        if line.startswith("init "):
            current = []
            blocks.append(current)
        elif current is not None:
            current.append(line[4:] if line.startswith("    ") else line)
    return ["\n".join(b) + "\n" for b in blocks]


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
        for block in python_blocks(text):
            exec(compile(block, path, "exec"), {})

    def test_installs_filter(self):
        self.run_built()
        self.assertIsNotNone(self.renpy.config.say_menu_text_filter)
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hello"), "Hello")
        self.assertTrue(self.renpy.display.log.lines)

    def test_chains_previous_filter(self):
        self.renpy.config.say_menu_text_filter = lambda s: s + "!"
        self.run_built()
        self.assertEqual(self.renpy.config.say_menu_text_filter("Hi"), "Hi!")


if __name__ == "__main__":
    unittest.main()
