from __future__ import unicode_literals

import renpy

from rtr import VERSION, settings
from rtr.google import GoogleClient, TranslateError
from rtr.translator import Translator

_STRING_TYPES = ("".__class__, b"".__class__)

_previous_filter = None
_translator = None
_cache = {}


def log(message):
    renpy.display.log.write("rtr: %s", message)


def character_names():
    names = set()
    for value in list(vars(renpy.store).values()):
        if not isinstance(value, renpy.character.ADVCharacter):
            continue
        name = getattr(value, "name", None)
        if isinstance(name, _STRING_TYPES) and "[" not in name:
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            names.add(name)
    return names


def glossary_terms():
    if not renpy.loader.loadable(settings.glossary_file):
        return set()
    f = renpy.loader.load(settings.glossary_file)
    try:
        data = f.read()
    finally:
        f.close()
    return set(line.strip() for line in data.decode("utf-8-sig").splitlines())


def collect_terms():
    terms = glossary_terms()
    if not settings.translate_names:
        terms |= character_names()
    return terms


def translate_line(text):
    if not text:
        return text
    cached = _cache.get(text)
    if cached is not None:
        return cached
    try:
        result = _translator.translate([text])[0]
    except TranslateError as e:
        log("translate failed: %s" % e)
        return text
    _cache[text] = result
    return result


def _filter(text):
    if _previous_filter is not None:
        text = _previous_filter(text)
    return translate_line(text)


def install():
    global _previous_filter, _translator
    percent = bool(getattr(renpy.config, "old_substitutions", False))
    terms = collect_terms()
    _translator = Translator(GoogleClient(), terms, percent)
    _previous_filter = renpy.config.say_menu_text_filter
    renpy.config.say_menu_text_filter = _filter
    log("%s installed, %d protected terms, percent=%s" % (VERSION, len(terms), percent))
