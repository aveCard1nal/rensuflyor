import io, json, os, pickle, struct, sys, zlib

class Stub(object):
    def __setstate__(self, state):
        if isinstance(state, tuple) and len(state) == 2:
            d, slots = state
            for s in (d, slots):
                if isinstance(s, dict):
                    self.__dict__.update(s)
        elif isinstance(state, dict):
            self.__dict__.update(state)

class StrStub(str):
    def __new__(cls, *args, **kw):
        s = args[0] if args else ""
        if isinstance(s, bytes):
            s = s.decode("utf-8", "replace")
        return str.__new__(cls, s)
    def __setstate__(self, state):
        pass

classes = {}

class U(pickle.Unpickler):
    def find_class(self, module, name):
        if module in ("__builtin__", "builtins", "copy_reg", "copyreg", "collections", "_codecs") and name not in ("object",):
            try:
                return pickle.Unpickler.find_class(self, module, name)
            except Exception:
                pass
        key = module + "." + name
        if key not in classes:
            if name in ("PyExpr",):
                base = StrStub
            elif "Dict" in name:
                base = dict
            elif "List" in name:
                base = list
            elif "Set" in name:
                base = set
            else:
                base = Stub
            classes[key] = type(name, (base,), {"_key": key})
        return classes[key]

def load(path):
    data = open(path, "rb").read()
    if data.startswith(b"RENPY RPC2"):
        pos = 10
        while True:
            slot, start, length = struct.unpack("III", data[pos:pos + 12])
            if slot == 0:
                raise ValueError("no slot 1")
            if slot == 1:
                raw = data[start:start + length]
                break
            pos += 12
    else:
        raw = data
    return U(io.BytesIO(zlib.decompress(raw)), encoding="utf-8", errors="replace").load()

def text(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v

def walk(obj, out, seen):
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, (list, tuple)):
        for x in obj:
            walk(x, out, seen)
        return
    if not isinstance(obj, Stub):
        return
    k = type(obj).__name__
    d = obj.__dict__
    if k == "Say" and d.get("what") is not None:
        out.append({"kind": "say", "who": text(d.get("who")), "what": text(d.get("what")), "loc": "%s:%s" % (text(d.get("filename")), d.get("linenumber"))})
    if k == "Menu":
        for item in d.get("items") or []:
            if item and item[0] is not None:
                out.append({"kind": "menu", "what": text(item[0]), "loc": "%s:%s" % (text(d.get("filename")), d.get("linenumber"))})
    for v in d.values():
        if isinstance(v, (list, tuple, Stub)):
            walk(v, out, seen)

if __name__ == "__main__":
    root, dest = sys.argv[1], sys.argv[2]
    out = []
    errors = 0
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if f.endswith(".rpyc"):
                try:
                    walk(load(os.path.join(dp, f)), out, set())
                except Exception as e:
                    errors += 1
                    print("ERR", f, repr(e)[:200])
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(out), "lines", errors, "errors")
