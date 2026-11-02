import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src", "rensuflyor")
SCREENS = os.path.join(ROOT, "src", "screens.rpy")
OUT = os.path.join(ROOT, "dist", "zz_rensuflyor.rpy")

USER_SETTINGS = [
    "provider",
    "translate_names",
    "settings_key",
    "font_fallback",
]

MODULES = [
    "rensuflyor",
    "rensuflyor.settings",
    "rensuflyor.tags",
    "rensuflyor.segment",
    "rensuflyor.codec",
    "rensuflyor.protect",
    "rensuflyor.fontcheck",
    "rensuflyor.client",
    "rensuflyor.google",
    "rensuflyor.yandex",
    "rensuflyor.translator",
    "rensuflyor.combine",
    "rensuflyor.cache",
    "rensuflyor.worker",
    "rensuflyor.lookahead",
    "rensuflyor.hooks",
]

LOADER = '''init -999 python hide:
    import sys
    import types

    def _load(name, source):
        if sys.version_info[0] == 2:
            name = name.encode("ascii")
        module = types.ModuleType(name)
        module.__file__ = "<%s>" % name
        if name == "rensuflyor":
            module.__path__ = []
        sys.modules[name] = module
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, module)
        exec(compile(source, module.__file__, "exec", 0, True), module.__dict__)

'''

INSTALL = '''
init 999 python hide:
    import rensuflyor.hooks
    rensuflyor.hooks.install()
'''


def module_path(name):
    parts = name.split(".")[1:]
    if not parts:
        return os.path.join(SRC, "__init__.py")
    return os.path.join(SRC, *parts) + ".py"


def read_source(name):
    with io.open(module_path(name), encoding="utf-8") as f:
        return f.read()


def settings_block():
    defaults = {}
    exec(compile(read_source("rensuflyor.settings"), "settings", "exec"), defaults)
    lines = ["init -998 python hide:\n", "    import rensuflyor.settings as s\n"]
    for name in USER_SETTINGS:
        lines.append("    s.%s = %r\n" % (name, defaults[name]))
    return "".join(lines) + "\n"


def build():
    lines = [settings_block(), LOADER]
    for name in MODULES:
        lines.append("    _load(%r, %r)\n" % (name, read_source(name)))
    lines.append(INSTALL)
    with io.open(SCREENS, encoding="utf-8") as f:
        lines.append(u"\n" + f.read())
    out_dir = os.path.dirname(OUT)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(u"".join(lines))
    return OUT


if __name__ == "__main__":
    path = build()
    sys.stdout.write("built %s\n" % path)
