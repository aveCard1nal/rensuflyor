from __future__ import unicode_literals

import io
import json
import os
import unittest

from rtr.codec import CodecError, decode, encode, html_unescape
from rtr.segment import split


def roundtrip(text, percent=False, translate=None):
    line = split(text, percent)
    done = {}
    for seg in line.segments:
        enc = encode(seg)
        html = translate(enc.html) if translate else enc.html
        done[id(seg)] = decode(html, enc, percent)
    return line.join(done)


def only(text, percent=False):
    segs = split(text, percent).segments
    assert len(segs) == 1, segs
    return encode(segs[0])


class SegmentTest(unittest.TestCase):

    def test_split_on_pauses(self):
        line = split("Well, here is the plan...{w=3}{nw}")
        self.assertEqual(len(line.segments), 1)
        self.assertEqual(line.segments[0].raw, "Well, here is the plan...")

    def test_split_on_newline(self):
        line = split("First line.\nSecond line.")
        self.assertEqual([s.raw for s in line.segments], ["First line.", "Second line."])

    def test_whitespace_kept_outside(self):
        seg = split("  Hello there. ").segments[0]
        self.assertEqual((seg.lead, seg.raw, seg.trail), ("  ", "Hello there.", " "))

    def test_untranslatable(self):
        self.assertEqual(split("... {w} ?!").segments, [])
        self.assertEqual(split("[name]").segments, [])

    def test_join_translated(self):
        line = split("One.{w} Two.")
        done = {}
        for seg, text in zip(line.segments, ["Раз.", "Два."]):
            done[id(seg)] = text
        self.assertEqual(line.join(done), "Раз.{w} Два.")


class EncodeTest(unittest.TestCase):

    def test_paired(self):
        self.assertEqual(only("Is it {b}the{/b} answer?").html, "Is it <span id=\"1\">the</span> answer?")

    def test_nested(self):
        enc = only("({color=#fff}{size=-2}KNIGHT{/size} reputation{/color})")
        self.assertEqual(enc.html, "(<span id=\"1\"><span id=\"2\">KNIGHT</span> reputation</span>)")

    def test_atoms(self):
        enc = only("Hey [name], {image=heart.png} ok")
        self.assertEqual(enc.html, "Hey <x id=\"1\"></x>, <x id=\"2\"></x> ok")

    def test_unpaired_tags_are_atoms(self):
        enc = encode(split("{i}Sighs{w} on").segments[0])
        self.assertEqual(enc.html, "<x id=\"1\"></x>Sighs")

    def test_self_closing_inside_pair(self):
        enc = only("{b}Hello {image=heart.png} there{/b}")
        self.assertEqual(enc.html, "<span id=\"1\">Hello <x id=\"2\"></x> there</span>")

    def test_non_bmp_entity(self):
        self.assertEqual(html_unescape("&#128512;"), u"\U0001F600")

    def test_crossed_tags(self):
        enc = only("{b}a{i}b{/b}c{/i}")
        self.assertEqual(sorted(enc.atoms.values()), ["{/b}", "{b}"])
        self.assertEqual(list(enc.opens.values()), ["{i}"])

    def test_html_chars_escaped(self):
        self.assertEqual(only("B&R <3").html, "B&amp;R &lt;3")


class DecodeTest(unittest.TestCase):

    def test_reordered_translation(self):
        enc = only("He is {b}very{/b} angry, [name].")
        out = decode("<x id=\"2\"></x>, он <span id=\"1\">очень</span> зол.", enc)
        self.assertEqual(out, "[name], он {b}очень{/b} зол.")

    def test_lenient_markup(self):
        enc = only("He is {b}very{/b} angry, [name].")
        out = decode("Он < SPAN ID = '1' >очень</ span> зол, <x id=2/>.", enc)
        self.assertEqual(out, "Он {b}очень{/b} зол, [name].")

    def test_entities_and_escaping(self):
        enc = only("B&R")
        self.assertEqual(decode("B&amp;R {нет} [да] &#1046;", enc), "B&R {{нет} [[да] Ж")

    def test_percent_reescaped(self):
        enc = only("It's 99%% me.", percent=True)
        self.assertEqual(enc.html, "It's 99% me.")
        self.assertEqual(decode("Это на 99% я.", enc, percent=True), "Это на 99%% я.")

    def test_missing_atom(self):
        enc = only("Hi [name].")
        self.assertRaises(CodecError, decode, "Привет.", enc)

    def test_duplicate_atom(self):
        enc = only("Hi [name].")
        self.assertRaises(CodecError, decode, "<x id=1></x> <x id=1></x>", enc)

    def test_unclosed_span(self):
        enc = only("{i}Hi{/i} there")
        self.assertRaises(CodecError, decode, "<span id=1>Привет", enc)

    def test_unknown_id(self):
        enc = only("{i}Hi{/i} there")
        self.assertRaises(CodecError, decode, "<span id=7>Привет</span>", enc)

    def test_unescape(self):
        self.assertEqual(html_unescape("&lt;&gt;&amp;&quot;&#39;&#x41;&bogus;"), "<>&\"'A&bogus;")


class RoundtripTest(unittest.TestCase):

    CASES = [
        "Plain line.",
        "*{i}Yawns{/i}* Is it morning already?",
        "The key? {b}That{/b} old key?",
        "{size=-[shrink]}See you next spring!{/size}",
        "Bow ({color=#ffffff}{size=-[persistent.ui_scale]}{font=fonts/x.ttf}KNIGHT{/font}{/size} reputation{/color})",
        "Splendid, truly splendid!{w=2}{nw}",
        "Pick a level. Expert level has 20%% fewer hints.\nNight theme dims the screen.",
        "Use {{braces} and [[brackets] here, [name].",
        "  Leading and trailing.  ",
        "{i}Open across{w} a pause{/i}",
        "",
    ]

    def test_identity(self):
        for case in self.CASES:
            for percent in (False, True):
                self.assertEqual(roundtrip(case, percent), case)

    def test_corpus(self):
        path = os.environ.get("RTR_CORPUS")
        if not path:
            self.skipTest("RTR_CORPUS not set")
        with io.open(path, encoding="utf-8") as f:
            lines = json.load(f)
        bad = []
        for item in lines:
            text = item["what"]
            if roundtrip(text, True) != text:
                bad.append(text)
        self.assertEqual(bad[:5], [])


if __name__ == "__main__":
    unittest.main()
