from __future__ import unicode_literals

import re
import unittest

from rtr.protect import clean_terms, compile_terms, protect
from rtr.segment import split
from rtr.translator import Translator, tidy_html

MARKUP = re.compile(r"(<[^>]*>)")


class FakeClient(object):

    def __init__(self, text=None, html=None, words=None):
        self.text = text
        self.html = html
        self.words = words or {}
        self.calls = []

    def _default(self, s):
        return "".join(p if p.startswith("<") else self.words.get(p, p.upper()) for p in MARKUP.split(s))

    def translate(self, texts, fmt="text"):
        self.calls.append((fmt, list(texts)))
        hook = self.text if fmt == "text" else self.html
        return [hook(t) if hook else self._default(t) for t in texts]


class ProtectTest(unittest.TestCase):

    def test_clean_terms(self):
        self.assertEqual(clean_terms(["Lily", " ", "[name]", "???", "Lily Ann", "50%"]), ["Lily Ann", "Lily"])

    def test_protect_splits_text(self):
        seg = split("Hi Lily, and Lilyanne.").segments[0]
        protect(seg, compile_terms(["Lily"]))
        self.assertEqual([t.raw for t in seg.tokens], ["Hi ", "Lily", ", and Lilyanne."])
        self.assertEqual(seg.raw, "Hi Lily, and Lilyanne.")

    def test_protect_keeps_escapes(self):
        seg = split("{{Lily} 5%% off", True).segments[0]
        protect(seg, compile_terms(["Lily"]), True)
        self.assertEqual(seg.raw, "{{Lily} 5%% off")

    def test_only_term_is_untranslatable(self):
        seg = split("Lily!").segments[0]
        protect(seg, compile_terms(["Lily"]))
        self.assertFalse(seg.translatable)


class TranslatorTest(unittest.TestCase):

    def test_text_mode(self):
        t = Translator(FakeClient())
        self.assertEqual(t.translate(["Is it {b}the{/b} answer, [name]?"]), ["IS IT {b}THE{/b} ANSWER, [name]?"])
        self.assertEqual(t.stats["text"], 1)

    def test_pauses_and_whitespace(self):
        t = Translator(FakeClient())
        self.assertEqual(t.translate([" Thanks!{w=2} Bye.{nw}"]), [" THANKS!{w=2} BYE.{nw}"])

    def test_terms_not_sent(self):
        client = FakeClient()
        t = Translator(client, ["Lily"])
        self.assertEqual(t.translate(["Hi Lily."]), ["HI Lily."])
        self.assertIn("<x id=\"1\"></x>", client.calls[0][1][0])

    def test_dedupes_requests(self):
        client = FakeClient()
        Translator(client).translate(["Same.", "Same.", "Other."])
        self.assertEqual(client.calls[0][1], ["Same.", "Other."])

    def test_html_fallback(self):
        client = FakeClient(text=lambda s: "сломано")
        t = Translator(client)
        self.assertEqual(t.translate(["Hey [name]."]), ["HEY [name]."])
        self.assertEqual([c[0] for c in client.calls], ["text", "html"])
        self.assertEqual(t.stats["html"], 1)

    def test_pieces_fallback(self):
        client = FakeClient(text=lambda s: "сломано" if "<" in s else s.upper(), html=lambda s: "сломано")
        t = Translator(client, percent=True)
        out = t.translate(["He is {b}very{/b} angry, [name]. 99%% sure."])
        self.assertEqual(out, ["HE IS {b}VERY{/b} ANGRY, [name]. 99%% SURE."])
        self.assertEqual(t.stats["pieces"], 1)
        self.assertEqual(client.calls[-1][1], ["He is", "very", "angry,", ". 99% sure."])

    def test_nothing_to_translate(self):
        client = FakeClient()
        self.assertEqual(Translator(client).translate(["...", "[name]!"]), ["...", "[name]!"])
        self.assertEqual(client.calls, [])

    def test_escapes_output(self):
        client = FakeClient(text=lambda s: "{скобки} [и] 5%")
        self.assertEqual(Translator(client, percent=True).translate(["Brackets."]), ["{{скобки} [[и] 5%%"])


class TidyTest(unittest.TestCase):

    def test_tidy(self):
        self.assertEqual(tidy_html("тебя,<x id=\"2\"></x> ."), "тебя, <x id=\"2\"></x>.")
        self.assertEqual(tidy_html("сделал</span> ?"), "сделал</span>?")
        self.assertEqual(tidy_html("бак ( <span id=\"1\">$</span> )"), "бак (<span id=\"1\">$</span>)")


if __name__ == "__main__":
    unittest.main()
