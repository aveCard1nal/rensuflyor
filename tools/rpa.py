import io, os, pickle, sys, zlib

class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError("forbidden global %s.%s" % (module, name))

def index(path):
    with open(path, "rb") as f:
        header = f.readline().split()
        offset = int(header[1], 16)
        key = int(header[2], 16)
        f.seek(offset)
        data = SafeUnpickler(io.BytesIO(zlib.decompress(f.read())), encoding="bytes").load()
    out = {}
    for name, parts in data.items():
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        p = parts[0]
        prefix = p[2] if len(p) > 2 else b""
        out[name] = (p[0] ^ key, p[1] ^ key, prefix)
    return out

def extract(path, dest, exts):
    idx = index(path)
    n = 0
    with open(path, "rb") as f:
        for name, (off, length, prefix) in idx.items():
            if not name.lower().endswith(exts):
                continue
            f.seek(off)
            body = prefix + f.read(length - len(prefix))
            target = os.path.join(dest, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as o:
                o.write(body)
            n += 1
    return n

if __name__ == "__main__":
    dest = sys.argv[1]
    for path in sys.argv[2:]:
        print(os.path.basename(path), extract(path, dest, (".rpy", ".rpyc")))
