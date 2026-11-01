from __future__ import unicode_literals

import io
import os
import sys
import time

import renpy

from rtr import VERSION, settings
from rtr.cache import Cache
from rtr.google import GoogleClient
from rtr.lookahead import collect
from rtr.translator import Translator
from rtr.worker import Worker

_STRING_TYPES = ("".__class__, b"".__class__)

_previous_filter = None
_worker = None
_cache = None
_last_node = None


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


def _writable(path):
    try:
        with io.open(path, "ab"):
            pass
        return True
    except (IOError, OSError):
        return False


def cache_path():
    for base in (renpy.config.gamedir, renpy.config.savedir):
        if base:
            path = os.path.join(base, settings.cache_file)
            if _writable(path):
                return path
    return None


def _apply_previous(text):
    if _previous_filter is None:
        return text
    try:
        return _previous_filter(text)
    except Exception:
        return text


def _needs_translation(text):
    return bool(text) and any(c.isalpha() for c in text)


def prefetch():
    global _last_node
    try:
        name = renpy.game.context().current
        if name == _last_node:
            return
        _last_node = name
        node = renpy.game.script.lookup(name)
    except Exception:
        return
    texts = collect(node, renpy.game.script.lookup, settings.lookahead)
    _worker.request([_apply_previous(t) for t in texts])


def translate_line(text):
    if not _needs_translation(text):
        return text
    cached = _cache.get(text)
    if cached is not None:
        prefetch()
        return cached
    prefetch()
    start = time.time()
    result = _worker.wait(text, settings.wait_timeout)
    if result is None:
        log("not ready after %.1fs, showing original" % (time.time() - start))
        return text
    return result


def _filter(text):
    return translate_line(_apply_previous(text))


def install():
    global _previous_filter, _worker, _cache
    old = getattr(sys, "_rtr_worker", None)
    if old is not None:
        old.stop()
    percent = bool(getattr(renpy.config, "old_substitutions", False))
    terms = collect_terms()
    _cache = Cache(cache_path())
    loaded = _cache.load()
    _worker = Worker(Translator(GoogleClient(), terms, percent), _cache, log)
    _worker.start()
    sys._rtr_worker = _worker
    _previous_filter = renpy.config.say_menu_text_filter
    renpy.config.say_menu_text_filter = _filter
    log("%s installed, %d protected terms, percent=%s, cache %s (%d entries)" % (VERSION, len(terms), percent, _cache.path, loaded))
