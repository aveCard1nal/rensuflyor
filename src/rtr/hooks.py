from __future__ import unicode_literals

import io
import os
import subprocess
import sys
import time

import renpy

from rtr import VERSION, settings
from rtr.cache import Cache
from rtr.fontcheck import has_cyrillic
from rtr.google import GoogleClient
from rtr.lookahead import collect
from rtr.translator import Translator
from rtr.worker import Worker
from rtr.yandex import YandexClient, new_ucid

_STRING_TYPES = ("".__class__, b"".__class__)

PROVIDERS = {
    "google": ("Google", GoogleClient),
    "yandex": ("Яндекс", YandexClient),
}

FONT_TRANSFORM = "rtr_cyrillic"
CYRILLIC_RANGES = ((0x0400, 0x052F), (0x2116, 0x2116))

_font_checks = {}
_font_groups = {}
_previous_filter = None
_worker = None
_cache = None
_last_node = None
_percent = False


def log(message):
    renpy.display.log.write("rtr: %s", message)


def _persistent():
    return renpy.game.persistent


def _get(name, default):
    value = getattr(_persistent(), "_rtr_" + name, None)
    return default if value is None else value


def _set(name, value):
    setattr(_persistent(), "_rtr_" + name, value)


def provider():
    name = _get("provider", settings.provider)
    return name if name in PROVIDERS else "google"


def translate_names():
    return bool(_get("translate_names", settings.translate_names))


def show_original():
    return bool(_get("show_original", False))


def ucid():
    value = _get("ucid", None)
    if not value:
        value = new_ucid()
        _set("ucid", value)
    return value


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


def glossary_path():
    return os.path.join(renpy.config.gamedir, settings.glossary_file)


def glossary_terms():
    path = glossary_path()
    if not os.path.exists(path):
        return set()
    with io.open(path, "rb") as f:
        data = f.read()
    return set(line.strip() for line in data.decode("utf-8-sig", "replace").splitlines())


def collect_terms():
    terms = glossary_terms()
    if not translate_names():
        terms |= character_names()
    return terms


def _writable(path):
    try:
        with io.open(path, "ab"):
            pass
        return True
    except (IOError, OSError):
        return False


def cache_path(name):
    filename = settings.cache_file % name
    for base in (renpy.config.gamedir, renpy.config.savedir):
        if base:
            path = os.path.join(base, filename)
            if _writable(path):
                return path
    return None


def make_client(name):
    cls = PROVIDERS[name][1]
    if cls is YandexClient:
        return YandexClient(ucid=ucid())
    return cls()


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
    prefetch()
    if show_original():
        return text
    cached = _cache.get(text)
    if cached is not None:
        return cached
    start = time.time()
    result = _worker.wait(text, settings.wait_timeout)
    if result is None:
        log("not ready after %.1fs, showing original" % (time.time() - start))
        return text
    return result


def _filter(text):
    return translate_line(_apply_previous(text))


def start():
    global _worker, _cache, _last_node
    old = getattr(sys, "_rtr_worker", None)
    if old is not None:
        old.stop()
    name = provider()
    terms = collect_terms()
    _cache = Cache(cache_path(name))
    loaded = _cache.load()
    _worker = Worker(Translator(make_client(name), terms, _percent), _cache, log)
    _worker.start()
    sys._rtr_worker = _worker
    _last_node = None
    log("%s using %s, %d protected terms, cache %s (%d entries)" % (VERSION, name, len(terms), _cache.path, loaded))


def set_provider(name):
    if name not in PROVIDERS or name == provider():
        return
    _set("provider", name)
    start()


def toggle_names():
    _set("translate_names", not translate_names())
    reload_terms()


def toggle_original():
    _set("show_original", not show_original())


def reload_terms():
    _worker.translator.set_terms(collect_terms())


def open_glossary():
    path = glossary_path()
    if not os.path.exists(path):
        with io.open(path, "wb"):
            pass
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        log("cannot open %s: %s" % (path, e))


def clear_cache():
    global _last_node
    _cache.clear()
    _worker.reset_failures()
    _last_node = None


def status():
    return {
        "provider": provider(),
        "providers": [(key, PROVIDERS[key][0]) for key in ("google", "yandex")],
        "translate_names": translate_names(),
        "show_original": show_original(),
        "cached": len(_cache),
        "error": _worker.last_error,
        "glossary": glossary_path(),
    }


def font_has_cyrillic(name):
    if name not in _font_checks:
        try:
            f = renpy.loader.load(name)
            try:
                data = f.read()
            finally:
                f.close()
            _font_checks[name] = has_cyrillic(data)
        except Exception:
            _font_checks[name] = False
        log("font %s has cyrillic: %s" % (name, _font_checks[name]))
    return _font_checks[name]


def cyrillic_font(font):
    key = font if isinstance(font, _STRING_TYPES) else id(font)
    rv = _font_groups.get(key)
    if rv is not None:
        return rv
    if isinstance(font, _STRING_TYPES) and font_has_cyrillic(font):
        rv = font
    else:
        rv = renpy.text.font.FontGroup()
        for start, end in CYRILLIC_RANGES:
            rv.add(settings.fallback_font, start, end)
        rv.add(font, None, None)
    _font_groups[key] = rv
    return rv


def install_font_fallback():
    if not settings.font_fallback:
        return
    renpy.config.font_transforms[FONT_TRANSFORM] = cyrillic_font
    prefs = renpy.game.preferences
    if getattr(prefs, "font_transform", None) in (None, FONT_TRANSFORM):
        prefs.font_transform = FONT_TRANSFORM


def install():
    global _previous_filter, _percent
    _percent = bool(getattr(renpy.config, "old_substitutions", False))
    start()
    _previous_filter = renpy.config.say_menu_text_filter
    renpy.config.say_menu_text_filter = _filter
    install_font_fallback()
    renpy.config.keymap["rtr_settings"] = [settings.settings_key]
    renpy.config.underlay.append(renpy.display.behavior.Keymap(rtr_settings=renpy.store.ToggleScreen("rtr_settings")))
    log("%s installed, percent=%s" % (VERSION, _percent))
