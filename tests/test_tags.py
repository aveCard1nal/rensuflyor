from __future__ import unicode_literals

import unittest

from rensuflyor.tags import BREAK, INTERP, TAG, TEXT, escape_text, tokenize


def kinds(tokens):
    return [(t.kind, t.raw) for t in tokens]


class TokenizeTest(unittest.TestCase):

    def test_plain(self):
        self.assertEqual(kinds(tokenize("Hello there.")), [(TEXT, "Hello there.")])

    def test_paired_tag(self):
        tokens = tokenize("Is it {b}the{/b} answer?")
        self.assertEqual(kinds(tokens), [
            (TEXT, "Is it "),
            (TAG, "{b}"),
            (TEXT, "the"),
            (TAG, "{/b}"),
            (TEXT, " answer?"),
        ])
        self.assertEqual(tokens[1].key, "b")
        self.assertFalse(tokens[1].closing)
        self.assertTrue(tokens[3].closing)

    def test_tag_with_value(self):
        tokens = tokenize("{color=#2b8ca3}7 coins{/color}")
        self.assertEqual(tokens[0].key, "color")
        self.assertEqual(tokens[2].key, "color")

    def test_tag_value_with_interpolation(self):
        tokens = tokenize("{size=-[shrink]}Small{/size}")
        self.assertEqual(kinds(tokens), [(TAG, "{size=-[shrink]}"), (TEXT, "Small"), (TAG, "{/size}")])

    def test_style_and_comment_keys(self):
        self.assertEqual(tokenize("{=big}x{/=big}")[0].key, "=big")
        self.assertEqual(tokenize("{#note}")[0].key, "#note")

    def test_interpolation(self):
        self.assertEqual(kinds(tokenize("Hi [name]!")), [(TEXT, "Hi "), (INTERP, "[name]"), (TEXT, "!")])

    def test_nested_interpolation(self):
        self.assertEqual(kinds(tokenize("[names[0]] here")), [(INTERP, "[names[0]]"), (TEXT, " here")])

    def test_escapes(self):
        tokens = tokenize("Use {{braces} and [[brackets]")
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].text, "Use {braces} and [brackets]")
        self.assertEqual(tokens[0].raw, "Use {{braces} and [[brackets]")

    def test_percent_disabled(self):
        self.assertEqual(tokenize("99%% me")[0].text, "99%% me")

    def test_percent_enabled(self):
        tokens = tokenize("99%% me, %(who)s", percent=True)
        self.assertEqual(kinds(tokens), [(TEXT, "99%% me, "), (INTERP, "%(who)s")])
        self.assertEqual(tokens[0].text, "99% me, ")

    def test_newline_is_break(self):
        self.assertEqual(kinds(tokenize("a\nb")), [(TEXT, "a"), (BREAK, "\n"), (TEXT, "b")])

    def test_split_tags(self):
        tokens = tokenize("Thanks!{w=2}{nw}")
        self.assertTrue(tokens[1].is_split())
        self.assertTrue(tokens[2].is_split())
        self.assertFalse(tokens[0].is_split())

    def test_unterminated(self):
        self.assertEqual(kinds(tokenize("a {b")), [(TEXT, "a {b")])
        self.assertEqual(kinds(tokenize("a [b")), [(TEXT, "a [b")])

    def test_escape_text(self):
        self.assertEqual(escape_text("{x} [y] 5%"), "{{x} [[y] 5%")
        self.assertEqual(escape_text("5%", percent=True), "5%%")


if __name__ == "__main__":
    unittest.main()
