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
        self.assertEqual(Translator(client, percent=True).translate(["Brackets."]), ["{{Скобки} [[и] 5%%"])


class FlakyClient(FakeClient):

    def translate(self, texts, fmt="text"):
        self.calls.append((fmt, list(texts)))
        if fmt != "text":
            raise IOError("429")
        return ["\u0441\u043b\u043e\u043c\u0430\u043d\u043e" if "<" in t else t.upper() for t in texts]


class RobustnessTest(unittest.TestCase):

    def test_keeps_good_lines_when_fallback_fails(self):
        t = Translator(FlakyClient())
        self.assertEqual(t.translate(["Good line.", "Hey [name]."]), ["GOOD LINE.", None])

    def test_first_request_failure_raises(self):
        class Down(FakeClient):
            def translate(self, texts, fmt="text"):
                raise IOError("down")
        self.assertRaises(IOError, Translator(Down()).translate, ["Hi."])

    def test_empty_result_falls_back(self):
        client = FakeClient(text=lambda s: "", html=lambda s: "\u041f\u0440\u0438\u0432\u0435\u0442.")
        self.assertEqual(Translator(client).translate(["Hello."]), ["\u041f\u0440\u0438\u0432\u0435\u0442."])

    def test_match_case(self):
        client = FakeClient(text=lambda s: "\u0438\u0433\u043d\u043e\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u044d\u0442\u043e")
        self.assertEqual(Translator(client).translate(["Ignore it"]), ["\u0418\u0433\u043d\u043e\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u044d\u0442\u043e"])
        client = FakeClient(text=lambda s: "\u0430 \u0442\u0430\u043a")
        self.assertEqual(Translator(client).translate(["and so"]), ["\u0430 \u0442\u0430\u043a"])

    def test_match_case_skips_markup(self):
        client = FakeClient(text=lambda s: "<span id=\"1\">\u0434\u0430</span>")
        self.assertEqual(Translator(client).translate(["{b}Yes{/b}"]), ["{b}\u0414\u0430{/b}"])


class TidyTest(unittest.TestCase):

    def test_tidy(self):
        self.assertEqual(tidy_html("тебя,<x id=\"2\"></x> ."), "тебя,<x id=\"2\"></x>.")
        src = "You, <x id=\"1\"></x> win. Aw...<x id=\"2\"></x>."
        self.assertEqual(tidy_html("Ты,<x id=\"1\"></x>победил. Ой... <x id=\"2\"></x>.", src),
                         "Ты, <x id=\"1\"></x> победил. Ой...<x id=\"2\"></x>.")
        self.assertEqual(tidy_html("Как<x id=\"1\"></x> атакует", "As <x id=\"1\"></x> attacks"), "Как <x id=\"1\"></x> атакует")
        self.assertEqual(tidy_html("сделал</span> ?"), "сделал</span>?")
        self.assertEqual(tidy_html("бак ( <span id=\"1\">$</span> )"), "бак (<span id=\"1\">$</span>)")


if __name__ == "__main__":
    unittest.main()
