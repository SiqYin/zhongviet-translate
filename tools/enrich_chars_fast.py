#!/usr/bin/env python3
"""Enrich single characters (threaded)."""
import json, re, html, pathlib, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = json.load(open(ROOT / "data" / "entries_raw.json", encoding="utf-8"))
chars = sorted({e["nom"] for e in E if e["is_char"]})
UA = {"User-Agent": "Mozilla/5.0 (compatible; HanVietDictBuilder/0.1)"}


def clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\u2009", "").strip()
    return re.sub(r"\s+", " ", s)


def one(ch):
    url = "https://old.chunom.org/pages/" + urllib.parse.quote(ch) + "/"
    req = urllib.request.Request(url, headers=UA)
    h = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
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
    m = re.search(r"\[([^\[\]]+)\]\s*<sup>north</sup>", h)
    if m:
        rec["ipa_n"] = clean(m.group(1))
    m = re.search(r"\[([^\[\]]+)\]\s*<sup>south</sup>", h)
    if m:
        rec["ipa_s"] = clean(m.group(1))
    m = re.search(r'class="ids-string">([^<]+)<', h)
    if m:
        rec["ids"] = clean(m.group(1))
    vs = re.findall(r'class="nom glyph-box" href="/pages/[0-9A-F]+/"[^>]*>\s*<span>&#x([0-9A-Fa-f]+);</span>', h)
    if vs:
        rec["variants"] = [chr(int(v, 16)) for v in vs]
    return ch, rec


out, ok, err = {}, 0, 0
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(one, c): c for c in chars}
    for f in as_completed(futs):
        try:
            ch, rec = f.result()
            out[ch] = rec
            ok += 1
        except Exception:
            err += 1
        if ok % 100 == 0:
            print(f"{ok}/{len(chars)}", flush=True)

json.dump(out, open(ROOT / "data" / "char_meta.json", "w", encoding="utf-8"), ensure_ascii=False)
print("ok", ok, "err", err, "ids", sum(1 for v in out.values() if v.get("ids")), flush=True)
