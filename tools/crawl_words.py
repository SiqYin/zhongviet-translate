#!/usr/bin/env python3
"""Crawl every character page on chunom.org (GitHub Pages) and harvest the compound words."""
import json, re, pathlib, urllib.request, html
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; HanVietDictBuilder/0.2)"}

sitemap = urllib.request.urlopen(
    urllib.request.Request("https://chunom.org/sitemap.xml", headers=UA), timeout=30
).read().decode("utf-8")
pages = sorted(set(re.findall(r"https://chunom\.org(/pages/[0-9A-Fa-f]{4,6}/)", sitemap)))
print("char pages:", len(pages), flush=True)

WORD_LI = re.compile(
    r'<li><span lang="vi">(.*?)</span><span><b>(.*?)</b>\s*[–-]\s*(.*?)</span></li>', re.S
)
IMG_ALT = re.compile(r'alt="([^"]*)"')


def one(path):
    url = "https://chunom.org" + path
    h = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read().decode("utf-8", "ignore")
    out = []
    for glyphs, vi, en in WORD_LI.findall(h):
        nom = "".join(IMG_ALT.findall(glyphs))
        vi = html.unescape(vi).strip()
        en = html.unescape(re.sub(r"<[^>]+>", "", en)).strip()
        if nom and vi:
            out.append((vi, nom, en))
    return out


words = {}
ok = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(one, p): p for p in pages}
    for f in as_completed(futs):
        try:
            for vi, nom, en in f.result():
                words.setdefault((vi.lower(), nom), {"vi": vi, "nom": nom, "en": en})
            ok += 1
        except Exception as e:
            pass
        if ok % 100 == 0:
            print(f"{ok}/{len(pages)} words={len(words)}", flush=True)

json.dump(list(words.values()), open(ROOT / "data" / "words_from_chars.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=0)
print("pages ok", ok, "unique words", len(words), flush=True)
