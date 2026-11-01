import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src", "rtr")
OUT = os.path.join(ROOT, "dist", "zz_autotranslate_ru.rpy")

USER_SETTINGS = [
    "translate_names",
]

MODULES = [
    "rtr",
    "rtr.settings",
    "rtr.tags",
    "rtr.segment",
    "rtr.codec",
    "rtr.protect",
    "rtr.google",
    "rtr.translator",
    "rtr.cache",
    "rtr.worker",
    "rtr.lookahead",
    "rtr.hooks",
]

LOADER = '''init -999 python hide:
    import sys
    import types

    def _load(name, source):
        if sys.version_info[0] == 2:
            name = name.encode("ascii")
        module = types.ModuleType(name)
        module.__file__ = "<%s>" % name
        if name == "rtr":
            module.__path__ = []
        sys.modules[name] = module
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, module)
        exec(compile(source, module.__file__, "exec", 0, True), module.__dict__)

'''

INSTALL = '''
init 999 python hide:
    import rtr.hooks
    rtr.hooks.install()
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
    exec(compile(read_source("rtr.settings"), "settings", "exec"), defaults)
    lines = ["init -998 python hide:\n", "    import rtr.settings as s\n"]
    for name in USER_SETTINGS:
        lines.append("    s.%s = %r\n" % (name, defaults[name]))
    return "".join(lines) + "\n"


def build():
    lines = [settings_block(), LOADER]
    for name in MODULES:
        lines.append("    _load(%r, %r)\n" % (name, read_source(name)))
    lines.append(INSTALL)
    out_dir = os.path.dirname(OUT)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(u"".join(lines))
    return OUT


if __name__ == "__main__":
    path = build()
    sys.stdout.write("built %s\n" % path)
