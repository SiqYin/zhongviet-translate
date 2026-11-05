#!/usr/bin/env python3
"""Step 2: enrich single characters with radical / strokes / IPA / IDS from old.chunom.org."""
import json, re, html, pathlib, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = json.load(open(ROOT / "data" / "entries_raw.json", encoding="utf-8"))
chars = [e for e in E if e["is_char"]]
print("chars to fetch:", len(chars), flush=True)

UA = {"User-Agent": "Mozilla/5.0 (compatible; HanVietDictBuilder/0.1)"}


def clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\u2009", "").strip()
    return re.sub(r"\s+", " ", s)


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


out = {}
for i, e in enumerate(chars, 1):
    ch = e["nom"]
    url = "https://old.chunom.org/pages/" + urllib.parse.quote(ch) + "/"
    try:
        h = fetch(url)
    except Exception as ex:
        print("ERR", ch, ex, flush=True)
        continue

    rec = {}
    m = re.search(r"Frequency</td><td>\s*<b>#(\d+)</b>", h)
    if m:
        rec["freq"] = int(m.group(1))
    m = re.search(r"Grade</td><td><a href=\"\.\./grade/(\d)/\">", h)
    if m:
        rec["grade"] = m.group(1)
    m = re.search(r"Strokes</td><td>(\d+)</td>", h)
    if m:
        rec["strokes"] = int(m.group(1))
    m = re.search(r'class="radical"[^>]*>&#x([0-9A-Fa-f]+);\s*\[(\d+)\.(\d+)\]', h)
    if m:
        rec["radical"] = chr(int(m.group(1), 16))
        rec["radical_no"] = int(m.group(2))
        rec["radical_var"] = int(m.group(3))
    m = re.search(r"\[([^\]]+)\]\s*<sup>north</sup>", h)
    if m:
        rec["ipa_n"] = clean(m.group(1))
    m = re.search(r"\[([^\]]+)\]\s*<sup>south</sup>", h)
    if m:
        rec["ipa_s"] = clean(m.group(1))
    m = re.search(r'class="ids-string">([^<]+)<', h)
    if m:
        rec["ids"] = clean(m.group(1))
    variants = re.findall(r'class="nom glyph-box" href="/pages/[0-9A-F]+/"[^>]*>\s*<span>&#x([0-9A-Fa-f]+);</span>', h)
    if variants:
        rec["variants"] = [chr(int(v, 16)) for v in variants]

    out[ch] = rec
    if i % 100 == 0:
        print(f"  {i}/{len(chars)}", flush=True)

json.dump(out, open(ROOT / "data" / "char_meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("fetched:", len(out), "with ids:", sum(1 for v in out.values() if v.get("ids")), flush=True)
