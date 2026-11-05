#!/usr/bin/env python3
"""Step 3: merge translations + char metadata -> app/data.js"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

entries = json.load(open(DATA / "entries_raw.json", encoding="utf-8"))
meta = {}
p = DATA / "char_meta.json"
if p.exists():
    meta = json.load(open(p, encoding="utf-8"))

# --- translation memory ---------------------------------------------------
zh_map = {}
for f in sorted((ROOT / "translate").glob("zh_*.txt")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        k, v = line.split("\t", 1)
        zh_map.setdefault(k.strip(), v.strip())

src = []
for f in sorted((ROOT / "translate").glob("src_*.txt")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            k, en = line.split("\t", 1)
            src.append((k.strip(), en.strip()))
gloss_zh = {}
for k, en in src:
    if k in zh_map:
        gloss_zh[en] = zh_map[k]

# --- OpenCC TS (traditional -> simplified) --------------------------------
ts = {}
for line in open(ROOT / "tools" / "opencc" / "TSCharacters.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        ts[parts[0]] = parts[1].split(" ")[0]

# --- OpenCC ST (simplified -> traditional), used to normalise Nom glyphs ---
st = {}
for line in open(ROOT / "tools" / "opencc" / "STCharacters.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        st[parts[0]] = parts[1].split(" ")[0]


def to_trad(text):
    return "".join(st.get(c, c) for c in text)


def to_simp(text):
    return "".join(ts.get(c, c) for c in text)


out = []
missing = 0
seen = {}
for e in entries:
    zh = gloss_zh.get(e["en"], "")
    if not zh:
        missing += 1
    m = meta.get(e["nom"], {}) if e["is_char"] else {}
    nom = to_trad(e["nom"])
    key = (e["vi"].lower(), nom)
    if key in seen:
        continue
    seen[key] = 1
    rec = {
        "i": e["id"],
        "v": e["vi"],
        "n": nom,
        "z": zh,
        "s": to_simp(zh),
        "e": e["en"],
        "g": e.get("grade", "0"),
        "f": e.get("freq_i", 999999),
        "t": 0 if e["is_char"] else 1,
    }
    strokes = e.get("strokes") or m.get("strokes")
    if strokes:
        rec["k"] = int(strokes)
    if m.get("radical"):
        rec["r"] = m["radical"]
    elif m.get("radical_no"):
        rec["r"] = chr(0x2F00 + int(m["radical_no"]) - 1)
    if m.get("radical_no"):
        rec["rn"] = int(m["radical_no"])
    if m.get("ids"):
        rec["d"] = m["ids"]
    ipa = " / ".join(x for x in [m.get("ipa_n"), m.get("ipa_s")] if x)
    if ipa:
        rec["p"] = ipa
    if m.get("variants"):
        rec["va"] = "".join(m["variants"])
    if e.get("freq") and str(e["freq"]).isdigit() and int(e["freq"]) < 999999:
        rec["f"] = int(e["freq"])
    if nom:
        rec["nf"] = nom[0]
        rec["nfs"] = to_simp(nom[0])
    out.append(rec)

out.sort(key=lambda r: (r["f"], 0 if r["t"] == 0 else 1, len(r["v"])))

# --- 字符层：IME 音節表中的 17,000+ 個字，只有讀音，沒有中文釋義 ----------
base = json.load(open(ROOT.parent / "base_chars.json", encoding="utf-8"))["dict"]
readings = {}
for part in base.split("|"):
    if ":" not in part:
        continue
    syl, cs = part.split(":", 1)
    syl = syl.strip()
    for c in cs.split(","):
        c = c.strip()
        if len(c) == 1:
            readings.setdefault(c, [])
            if syl not in readings[c]:
                readings[c].append(syl)

have = {r["n"] for r in out}
# 已有字條：補上其他讀音
for r in out:
    if r["t"] == 0:
        extra = [s for s in readings.get(r["n"], []) if s != r["v"]]
        if extra:
            r["vs"] = [r["v"]] + extra[:5]

added = 0
for ch, syls in readings.items():
    if ch in have or not syls:
        continue
    tv = to_trad(ch)
    if tv != ch and tv in have:      # 簡體異體，已有對應的繁體字條
        continue
    m = meta.get(ch, {})
    rec = {
        "i": "c%05d" % (added + 1),
        "v": syls[0],
        "n": ch,
        "z": "",
        "s": "",
        "e": "",
        "g": "0",
        "f": 999999,
        "t": 2,
    }
    if len(syls) > 1:
        rec["vs"] = syls[:6]
    if m.get("ids"):
        rec["d"] = m["ids"]
    if m.get("radical_no"):
        rec["r"] = chr(0x2F00 + int(m["radical_no"]) - 1)
        rec["rn"] = int(m["radical_no"])
    if m.get("strokes"):
        rec["k"] = m["strokes"]
    out.append(rec)
    added += 1

out.sort(key=lambda r: (r["f"], 0 if r["t"] == 0 else (1 if r["t"] == 1 else 2), len(r["v"])))

app = ROOT / "app"
app.mkdir(exist_ok=True)
payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
(app / "data.js").write_text("window.DICT=" + payload + ";\n", encoding="utf-8")

print(f"entries={len(out)} translated={len(out)-missing} missing={missing}")
print(f"data.js={len(payload)/1024:.0f} KB")
print("chars:", sum(1 for r in out if r['t'] == 0), "words:", sum(1 for r in out if r['t'] == 1))
print("with ids:", sum(1 for r in out if 'd' in r), "with ipa:", sum(1 for r in out if 'p' in r))
