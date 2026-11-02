from __future__ import absolute_import, unicode_literals

import io
import os
import subprocess
import sys
import time

import renpy

from rensuflyor import VERSION, settings
from rensuflyor.cache import Cache
from rensuflyor.client import describe
from rensuflyor.combine import combine
from rensuflyor.fontcheck import has_cyrillic
from rensuflyor.google import GoogleClient
from rensuflyor.lookahead import collect, kind_of, texts_of
from rensuflyor.protect import compile_terms
from rensuflyor.translator import Translator
from rensuflyor.worker import Worker
from rensuflyor.yandex import YandexClient, new_ucid

_STRING_TYPES = ("".__class__, b"".__class__)

PROVIDERS = {
    "google": ("Google", GoogleClient),
    "yandex": ("Яндекс", YandexClient),
}

FONT_TRANSFORM = "rensuflyor_cyrillic"
CYRILLIC_RANGES = ((0x0400, 0x052F), (0x2116, 0x2116))

_font_checks = {}
_font_groups = {}
_previous_filter = None
_worker = None
_cache = None
_last_node = None
_said_node = None
_call_depth = 0
_percent = False


def log(message):
    renpy.display.log.write("rensuflyor: %s", message)


def _persistent():
    return renpy.game.persistent


def _get(name, default):
    value = getattr(_persistent(), "_rensuflyor_" + name, None)
    return default if value is None else value


def _set(name, value):
    setattr(_persistent(), "_rensuflyor_" + name, value)
    try:
        renpy.exports.save_persistent()
    except Exception as e:
        log("cannot save persistent: %s" % (e,))


def provider():
    name = _get("provider", settings.provider)
    return name if name in PROVIDERS else "google"


def translate_names():
    return bool(_get("translate_names", settings.translate_names))


def translation_enabled():
    return not _get("disabled", False)


def show_both():
    return bool(_get("show_both", False))


def font_single():
    return bool(_get("font_single", False))


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
        if getattr(value, "dynamic", False):
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


def official_russian():
    try:
        lang = renpy.game.preferences.language
    except Exception:
        return False
    if not lang:
        return False
    lang = lang.lower()
    return lang in ("ru", "rus") or "russ" in lang or "русск" in lang


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
    lookup = renpy.game.script.lookup
    texts = collect(node, lookup, settings.lookahead)
    try:
        stack = renpy.game.context().return_stack
        if stack:
            site = lookup(stack[-1])
            texts += texts_of(site) + collect(site, lookup, settings.lookahead // 2)
    except Exception:
        pass
    _worker.request([_apply_previous(t) for t in texts])


def _predicting():
    try:
        return bool(renpy.display.predict.predicting)
    except Exception:
        return False


def _current_node():
    try:
        return renpy.game.script.lookup(renpy.game.context().current)
    except Exception:
        return None


def translate_line(text):
    if not _needs_translation(text) or not translation_enabled() or official_russian():
        return text
    if _predicting():
        result = _cache.get(text)
        if result is None:
            _worker.request([text])
            return text
        return result
    prefetch()
    node = _current_node()
    kind = kind_of(node) if node is not None else None
    if kind == "Menu":
        _worker.request([_apply_previous(t) for t in texts_of(node)], urgent=True)
    result = _cache.get(text)
    if result is None:
        start = time.time()
        result = _worker.wait(text, settings.wait_timeout)
        if result is None:
            log("not ready after %.1fs, showing original" % (time.time() - start))
            return text
    if show_both() and not (kind == "Say" and getattr(node, "who", None) == "extend"):
        return combine(result, text, _percent, inline=kind == "Menu")
    return result


def _filter(text):
    global _said_node
    if not _predicting():
        try:
            _said_node = renpy.game.context().current
        except Exception:
            _said_node = None
    return translate_line(_apply_previous(text))


def _from_python():
    try:
        return renpy.game.context().current != _said_node
    except Exception:
        return False


def _wrap_call(original):
    def call(self, what, *args, **kwargs):
        global _call_depth
        if _call_depth == 0 and isinstance(what, "".__class__) and _from_python():
            try:
                what = translate_line(_apply_previous(what))
            except Exception as e:
                log("python say failed: %s" % describe(e))
        _call_depth += 1
        try:
            return original(self, what, *args, **kwargs)
        finally:
            _call_depth -= 1
    call._rensuflyor_original = original
    return call


def install_character_call():
    cls = renpy.character.ADVCharacter
    original = getattr(cls.__call__, "_rensuflyor_original", cls.__call__)
    cls.__call__ = _wrap_call(original)


def start():
    global _worker, _cache, _last_node
    old = getattr(sys, "_rensuflyor_worker", None)
    if old is not None:
        old.stop()
    name = provider()
    terms = collect_terms()
    _cache = Cache(cache_path(name))
    loaded = _cache.load()
    _worker = Worker(Translator(make_client(name), terms, _percent), _cache, log)
    _worker.start()
    sys._rensuflyor_worker = _worker
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


def toggle_enabled():
    _set("disabled", translation_enabled())


def toggle_both():
    _set("show_both", not show_both())


def toggle_font_single():
    _set("font_single", not font_single())
    _font_groups.clear()


def reload_terms():
    old = set(getattr(_worker.translator, "terms", None) or ())
    new = collect_terms()
    _worker.translator.set_terms(new)
    changed = compile_terms(old ^ new)
    if changed is None:
        return
    stale = [src for src in list(_cache.entries) if changed.search(src)]
    try:
        _cache.forget(stale)
    except (IOError, OSError) as e:
        _report("не удалось обновить кэш: %s" % describe(e))
    log("terms changed, %d cached lines will be translated again" % len(stale))


def _report(message):
    log(message)
    _worker.last_error = message


def open_glossary():
    path = glossary_path()
    try:
        if not os.path.exists(path):
            with io.open(path, "wb"):
                pass
        if hasattr(os, "startfile"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        _report("не удалось открыть %s: %s" % (path, describe(e)))


def clear_cache():
    global _last_node
    try:
        _cache.clear()
    except (IOError, OSError) as e:
        _report("не удалось удалить кэш: %s" % describe(e))
    _worker.reset_failures()
    _last_node = None


def status():
    return {
        "provider": provider(),
        "providers": [(key, PROVIDERS[key][0]) for key in ("google", "yandex")],
        "translate_names": translate_names(),
        "enabled": translation_enabled(),
        "show_both": show_both(),
        "font_fallback": settings.font_fallback,
        "font_single": font_single(),
        "cached": len(_cache),
        "error": (_worker.last_error or "").replace("{", "{{"),
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
    elif font_single():
        rv = settings.fallback_font
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
    current = getattr(prefs, "font_transform", None)
    if current is None or current == FONT_TRANSFORM or current not in renpy.config.font_transforms:
        prefs.font_transform = FONT_TRANSFORM


def install():
    global _previous_filter, _percent
    try:
        _percent = bool(getattr(renpy.config, "old_substitutions", False))
        start()
        _previous_filter = renpy.config.say_menu_text_filter
        renpy.config.say_menu_text_filter = _filter
    except Exception as e:
        log("install failed, translation disabled: %s" % describe(e))
        return
    for step in (install_character_call, install_font_fallback, install_key):
        try:
            step()
        except Exception as e:
            log("%s failed: %s" % (step.__name__, describe(e)))
    log("%s installed, percent=%s" % (VERSION, _percent))


def install_key():
    renpy.config.keymap["rensuflyor_settings"] = [settings.settings_key]
    renpy.config.underlay.append(renpy.display.behavior.Keymap(rensuflyor_settings=renpy.store.ToggleScreen("rensuflyor_settings")))
