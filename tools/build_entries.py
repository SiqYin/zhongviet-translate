#!/usr/bin/env python3
"""Step 1: merge chunom.org sources into one raw entry list."""
import csv, json, re, unicodedata, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


entries = []
seen = set()


def add(vi, nom, en, grade="0", strokes="", freq="", uni="", standard="", source=""):
    vi, nom, en = norm(vi), norm(nom), norm(en)
    if not vi or not nom:
        return
    if vi.lower() in ("none", "null") or not en or en.lower() in ("none", "null"):
        return
    key = (vi.lower(), nom)
    if key in seen:
        return
    seen.add(key)
    entries.append({
        "vi": vi,
        "vi_norm": vi.lower(),
        "nom": nom,
        "en": en,
        "grade": str(grade or "0"),
        "strokes": strokes,
        "freq": freq,
        "unicode": uni,
        "standard": standard == "standard",
        "source": source,
        "is_char": len(nom) == 1,
        "syllables": [s for s in vi.split(" ") if s],
    })


# --- dict.csv -------------------------------------------------------------
with open(ROOT / "dict.csv", encoding="utf-8") as f:
    for row in csv.reader(f):
        if len(row) < 3:
            continue
        vi, nom, en = row[0], row[1], row[2]
        if len(row) >= 8:
            add(vi, nom, en, row[3], row[4], row[5], row[6], row[7], "dict.csv")
        elif len(row) >= 6:
            add(vi, nom, en, row[3], "", row[5] if row[5] else "", "", "", "dict.csv")
        else:
            add(vi, nom, en, "0", "", "", "", "", "dict.csv")

print("after dict.csv:", len(entries))

# --- standard-list.tsv ----------------------------------------------------
std = ROOT / "std_list.tsv"
if std.exists():
    with open(std, encoding="utf-8") as f:
        rdr = csv.reader(f, delimiter="\t")
        next(rdr, None)
        for row in rdr:
            if len(row) < 6:
                continue
            uni, freq, text, qn, en = row[1], row[2], row[3], row[4], row[5]
            if not text or not qn:
                continue
            add(qn, text, en, "0", "", freq if freq and freq != "9999999" else "", uni.replace("U+", ""), "standard", "std_list")

print("after std_list:", len(entries))

# --- enrich: canonical standard flag, sort key ----------------------------
for e in entries:
    e["len"] = len(e["syllables"])
    e["freq_i"] = int(e["freq"]) if str(e["freq"]).isdigit() else 999999
    e["id"] = f"e{len([x for x in entries[:entries.index(e)]]) + 1:05d}"

# stable ids
for i, e in enumerate(entries, 1):
    e["id"] = f"e{i:05d}"

json.dump(entries, open(OUT / "entries_raw.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

chars = [e for e in entries if e["is_char"]]
words = [e for e in entries if not e["is_char"]]
print(f"total={len(entries)} chars={len(chars)} words={len(words)}")
print("distinct glosses:", len({e['en'] for e in entries}))
