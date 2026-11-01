from __future__ import unicode_literals

import unittest

from rtr.combine import ORIGINAL_CLOSE, ORIGINAL_OPEN, combine, strip_control


def orig(text):
    return ORIGINAL_OPEN + text + ORIGINAL_CLOSE


class CombineTest(unittest.TestCase):

    def test_plain(self):
        self.assertEqual(combine("Привет.", "Hello."), "Привет.\n" + orig("Hello."))

    def test_inline(self):
        self.assertEqual(combine("Игнорировать", "Ignore it", inline=True), "Игнорировать / " + orig("Ignore it"))

    def test_same_text_not_doubled(self):
        self.assertEqual(combine("...", "..."), "...")

    def test_keeps_markup(self):
        self.assertEqual(combine("Это {b}наша{/b} [name].", "It's {b}our{/b} [name]."),
                         "Это {b}наша{/b} [name].\n" + orig("It's {b}our{/b} [name]."))

    def test_nw_moves_to_end(self):
        self.assertEqual(combine("Превосходно, просто превосходно!{w=2}{nw}", "Splendid, truly splendid!{w=2}{nw}"),
                         "Превосходно, просто превосходно!{w=2}\n" + orig("Splendid, truly splendid!") + "{nw}")

    def test_pauses_removed_from_original(self):
        self.assertEqual(combine("Раз.{w} Два.{p}Три.", "One.{w} Two.{p}Three."),
                         "Раз.{w} Два.{p}Три.\n" + orig("One. Two.Three."))

    def test_percent_and_escapes(self):
        self.assertEqual(combine("На 99%% {{точно}.", "99%% {{sure}.", True),
                         "На 99%% {{точно}.\n" + orig("99%% {{sure}."))

    def test_strip_control_keeps_style_tags(self):
        self.assertEqual(strip_control("{fast}{i}a{/i}{w=1}b{nw}"), "{i}a{/i}b")


if __name__ == "__main__":
    unittest.main()
