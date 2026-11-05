#!/usr/bin/env python3
"""Build the Chinese -> Vietnamese dictionary from CVDICT (CC BY-SA 4.0)."""
import json, re, csv, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "cvdict.u8"

# ---------- Hán-Việt readings ----------
hv = {}
for row in csv.reader(open(ROOT.parent / "hanviet.csv", encoding="utf-8")):
    if not row or row[0] == "char":
        continue
    ch, vals, py = row[0], row[1], row[2]
    lst = re.findall(r"'([^']*)'", vals)
    if not lst:
        continue
    hv[(ch, py)] = lst[0]
    hv.setdefault((ch, "*"), lst[0])

# ---------- pinyin tone marks ----------
MARKS = {"a": "āáǎà", "o": "ōóǒò", "e": "ēéěè", "i": "īíǐì", "u": "ūúǔù", "ü": "ǖǘǚǜ"}


def syllable(py):
    m = re.match(r"^([A-Za-zü:]+)([0-5])?$", py)
    if not m:
        return py
    body, tone = m.group(1).replace("u:", "ü").replace("v", "ü"), m.group(2)
    if not tone or tone in "50":
        return body
    t = int(tone) - 1
    low = body.lower()
    if "a" in low:
        idx = low.index("a")
    elif "e" in low:
        idx = low.index("e")
    elif "ou" in low:
        idx = low.index("o")
    else:
        vs = [i for i, c in enumerate(low) if c in "aeiouü"]
        if not vs:
            return body
        idx = vs[-1]
    return body[:idx] + MARKS[low[idx]][t] + body[idx + 1:]


def pinyin_display(py):
    out = " ".join(syllable(x) for x in py.split())
    return out[:1].lower() + out[1:]


# ---------- Vietnamese -> Nôm ----------
vi_nom = {}
entries = json.load(open(ROOT / "data" / "entries_raw.json", encoding="utf-8"))
for e in entries:
    vi_nom.setdefault(e["vi"].lower(), e["nom"])

CLS = re.compile(r"LT:.*$")
SLANG = re.compile(r"^\((tiếng lóng|từ lóng|khẩu ngữ|văn học|cũ|đph|phương ngữ)\)", re.I)
SURNAME = re.compile(r"^họ\s*\[", re.I)


NOTE = re.compile(r"^(dùng trong|lượng từ|xem |cũng viết|viết tắt|biến thể của|cách viết khác)", re.I)


def clean_sense(s):
    s = CLS.sub("", s).strip()
    s = re.sub(r"\s*\([^()]*\)\s*$", "", s)
    s = s.strip(" ;,.")
    if NOTE.match(s):
        return ""
    return s


merged = {}
for line in open(SRC, encoding="utf-8"):
    if not line.strip() or line.startswith("#"):
        continue
    m = re.match(r"(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$", line)
    if not m:
        continue
    trad, simp, py, gloss = m.groups()

    senses = [clean_sense(x) for x in gloss.split("/")]
    senses = [x for x in senses if x and not x.lower().startswith("lt:")]
    if not senses:
        continue

    rec = merged.setdefault(simp, {"simp": simp, "trads": [], "py": py, "pyc": {}, "senses": []})
    rec["pyc"][py] = rec["pyc"].get(py, 0) + 1
    if trad not in rec["trads"]:
        rec["trads"].append(trad)
    for x in senses:
        if x not in rec["senses"]:
            rec["senses"].append(x)

rows = []
for simp, e in merged.items():
    trads = e["trads"]
    trad = simp if simp in trads else trads[0]

    def rank(s):
        if SURNAME.match(s):
            return 3
        if SLANG.match(s):
            return 2
        return 1

    senses = sorted(e["senses"], key=lambda s: (rank(s), len(s.split())))
    py = max(e["pyc"].items(), key=lambda kv: kv[1])[0] if e["pyc"] else e["py"]
    pys = py.split()
    hanviet = ""
    if len(pys) == len(simp):
        rs = []
        for ch, p in zip(simp, pys):
            r = hv.get((ch, p)) or hv.get((ch, "*"))
            if not r:
                rs = []
                break
            rs.append(r)
        hanviet = " ".join(rs)

    nom = ""
    for s in senses:
        key = s.lower()
        if key in vi_nom:
            nom = vi_nom[key]
            break

    rows.append([trad, simp, pinyin_display(py), "；".join(senses[:5]), hanviet, nom])

rows.sort(key=lambda r: (len(r[1]), r[1]))
payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
(ROOT / "app").mkdir(exist_ok=True)
(ROOT / "app" / "zhvi.js").write_text("window.ZV=" + payload + ";\n", encoding="utf-8")

print("entries", len(rows))
print("with hanviet", sum(1 for r in rows if r[4]))
print("with nom", sum(1 for r in rows if r[5]))
print("size MB %.1f" % (len(payload.encode()) / 1024 / 1024))
