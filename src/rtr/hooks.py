import renpy

from rtr import VERSION

_previous_filter = None


def translate_line(text):
    return text


def _filter(text):
    if _previous_filter is not None:
        text = _previous_filter(text)
    return translate_line(text)


def install():
    global _previous_filter
    _previous_filter = renpy.config.say_menu_text_filter
    renpy.config.say_menu_text_filter = _filter
    renpy.display.log.write("rtr %s installed" % VERSION)
