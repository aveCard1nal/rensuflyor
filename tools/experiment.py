import io, json, os, random, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from rensuflyor.segment import split
from rensuflyor.codec import encode, decode, CodecError
from rensuflyor.tags import INTERP
from rensuflyor.google import GoogleClient
from rensuflyor.yandex import YandexClient

CORPUS, OUT = sys.argv[1], sys.argv[2]
lines = json.load(open(CORPUS, encoding="utf-8"))
random.seed(7)
seen = set()
def pick(pred, n):
    pool = [l["what"] for l in lines if pred(l["what"]) and l["what"] not in seen]
    random.shuffle(pool)
    out = pool[:n]
    seen.update(out)
    return out
groups = {
    "i": pick(lambda w: "{i}" in w and len(w) > 30, 50),
    "b": pick(lambda w: "{b}" in w, 30),
    "style": pick(lambda w: re.search(r"\{(color|size|font)", w), 30),
    "interp": pick(lambda w: "[" in w and "{" not in w and "[[" not in w, 60),
    "pause": pick(lambda w: "{w" in w, 15),
    "newline": pick(lambda w: "\n" in w, 10),
    "percent": pick(lambda w: "%%" in w, 10),
}

def s3_encode(seg, enc):
    html = enc.html
    for n, raw in enc.atoms.items():
        if raw.startswith("[") or raw.startswith("%("):
            inner = re.sub(r"[^A-Za-z]", "", raw.split("!")[0].split(":")[0]) or "X"
            html = html.replace('<x id="%d"></x>' % n, '<span id="%d" translate="no">%s</span>' % (n, inner))
    return html

def s3_back(html, enc):
    for n in enc.atoms:
        html = re.sub(r'<span[^>]*id\s*=\s*"?%d"?[^>]*translate[^>]*>.*?</span>' % n, '<x id="%d"></x>' % n, html)
        html = re.sub(r'<span[^>]*translate[^>]*id\s*=\s*"?%d"?[^>]*>.*?</span>' % n, '<x id="%d"></x>' % n, html)
    return html

CLIENTS = {"google": GoogleClient, "yandex": YandexClient}
client = CLIENTS[sys.argv[3] if len(sys.argv) > 3 else "google"]()


def google(qs, fmt):
    return client.translate(qs, fmt)

items = []
for g, ws in groups.items():
    for w in ws:
        line = split(w, True)
        for seg in line.segments:
            items.append((g, w, seg, encode(seg)))

schemes = {
    "S1_html": ("html", lambda seg, enc: enc.html, lambda h, enc: h),
    "S2_text": ("text", lambda seg, enc: enc.html, lambda h, enc: h),
    "S3_html_name": ("html", s3_encode, s3_back),
}
results = {}
for name, (fmt, enc_fn, back_fn) in schemes.items():
    out = []
    for i in range(0, len(items), 20):
        chunk = items[i:i + 20]
        qs = [enc_fn(seg, enc) for g, w, seg, enc in chunk]
        tr = google(qs, fmt)
        for (g, w, seg, enc), q, t in zip(chunk, qs, tr):
            try:
                d = decode(back_fn(t, enc), enc, True)
                ok = True
            except CodecError as e:
                d = "ERR " + str(e)
                ok = False
            out.append({"group": g, "src": seg.raw, "sent": q, "got": t, "decoded": d, "ok": ok})
        time.sleep(1.0)
    results[name] = out
json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("segments", len(items))
for name, out in results.items():
    by = {}
    for r in out:
        by.setdefault(r["group"], [0, 0])
        by[r["group"]][0] += r["ok"]
        by[r["group"]][1] += 1
    tot = sum(r["ok"] for r in out)
    print(name, "%d/%d" % (tot, len(out)), " ".join("%s=%d/%d" % (k, a, b) for k, (a, b) in by.items()))
