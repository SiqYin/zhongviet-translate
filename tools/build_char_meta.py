#!/usr/bin/env python3
"""Build char_meta.json for every character in the IME table + our entries.
Sources: cjkvi-ids (IDS) and Unihan_IRGSources (radical / strokes)."""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIHAN = ROOT.parent / "Unihan_IRGSources.txt"

entries = json.load(open(ROOT / "data" / "entries_raw.json", encoding="utf-8"))
chars = {e["nom"] for e in entries if e["is_char"]}

base = json.load(open(ROOT.parent / "base_chars.json", encoding="utf-8"))["dict"]
for part in base.split("|"):
    if ":" not in part:
        continue
    for c in part.split(":", 1)[1].split(","):
        c = c.strip()
        if len(c) == 1:
            chars.add(c)
print("chars to describe:", len(chars), flush=True)

ids = {}
for line in open(ROOT / "ids.txt", encoding="utf-8"):
    if line.startswith("#") or "\t" not in line:
        continue
    p = line.rstrip("\n").split("\t")
    if len(p) >= 3 and p[2] and p[2] != p[1]:
        ids[p[1]] = p[2]

rad, strokes = {}, {}
for line in open(UNIHAN, encoding="utf-8"):
    if "\tkRSUnicode\t" in line:
        cp, _, v = line.rstrip("\n").split("\t")
        rad[chr(int(cp[2:], 16))] = v
    elif "\tkTotalStrokes\t" in line:
        cp, _, v = line.rstrip("\n").split("\t")
        strokes[chr(int(cp[2:], 16))] = int(v.split(" ")[0])

meta = {}
for ch in chars:
    rec = {}
    if ch in ids:
        rec["ids"] = ids[ch]
    if ch in rad:
        m = re.match(r"(\d+)", rad[ch])
        if m:
            rec["radical_no"] = int(m.group(1))
    if ch in strokes:
        rec["strokes"] = strokes[ch]
    if rec:
        meta[ch] = rec

json.dump(meta, open(ROOT / "data" / "char_meta.json", "w", encoding="utf-8"), ensure_ascii=False)
print("meta", len(meta), "ids", sum(1 for v in meta.values() if "ids" in v),
      "strokes", sum(1 for v in meta.values() if "strokes" in v))
