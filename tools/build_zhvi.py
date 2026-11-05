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

# ---------- 簡 -> 繁（用於查漢越音） ----------
st = {}
for line in open(ROOT / "tools" / "opencc" / "STCharacters.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        st[parts[0]] = parts[1].split(" ")[0]


def to_trad(t):
    return "".join(st.get(c, c) for c in t)


# ---------- Unihan 漢越音（優先） ----------
KVIET = {}
for line in open(ROOT.parent / "Unihan_Readings.txt", encoding="utf-8"):
    if "\tkVietnamese\t" in line:
        cp, _, v = line.rstrip("\n").split("\t")
        KVIET[chr(int(cp[2:], 16))] = v

# ---------- Unihan 普通話讀音（單字定音） ----------
MANDARIN = {}
for line in open(ROOT.parent / "Unihan_Readings.txt", encoding="utf-8"):
    if "\tkMandarin\t" in line:
        cp, _, v = line.rstrip("\n").split("\t")
        MANDARIN[chr(int(cp[2:], 16))] = v.split(" ")[0]

ACCENT = {"ā":"a","á":"a","ǎ":"a","à":"a","ē":"e","é":"e","ě":"e","è":"e","ī":"i","í":"i",
          "ǐ":"i","ì":"i","ō":"o","ó":"o","ǒ":"o","ò":"o","ū":"u","ú":"u","ǔ":"u","ù":"u",
          "ǖ":"ü","ǘ":"ü","ǚ":"ü","ǜ":"ü","ń":"n","ň":"n","ǹ":"n","ḿ":"m"}


def strip_tone(s):
    return "".join(ACCENT.get(c, c) for c in s if not c.isdigit())


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



# ---------- pinyin -> zhuyin ----------
INITIALS = [("zh","ㄓ"),("ch","ㄔ"),("sh","ㄕ"),("b","ㄅ"),("p","ㄆ"),("m","ㄇ"),("f","ㄈ"),
            ("d","ㄉ"),("t","ㄊ"),("n","ㄋ"),("l","ㄌ"),("g","ㄍ"),("k","ㄎ"),("h","ㄏ"),
            ("j","ㄐ"),("q","ㄑ"),("x","ㄒ"),("r","ㄖ"),("z","ㄗ"),("c","ㄘ"),("s","ㄙ")]
FINALS = {"a":"ㄚ","o":"ㄛ","e":"ㄜ","ê":"ㄝ","ai":"ㄞ","ei":"ㄟ","ao":"ㄠ","ou":"ㄡ",
          "an":"ㄢ","en":"ㄣ","ang":"ㄤ","eng":"ㄥ","er":"ㄦ","i":"ㄧ","ia":"ㄧㄚ",
          "ie":"ㄧㄝ","iao":"ㄧㄠ","iu":"ㄧㄡ","ian":"ㄧㄢ","in":"ㄧㄣ","iang":"ㄧㄤ",
          "ing":"ㄧㄥ","iong":"ㄩㄥ","u":"ㄨ","ua":"ㄨㄚ","uo":"ㄨㄛ","uai":"ㄨㄞ",
          "ui":"ㄨㄟ","uan":"ㄨㄢ","un":"ㄨㄣ","uang":"ㄨㄤ","ong":"ㄨㄥ","ü":"ㄩ",
          "üe":"ㄩㄝ","üan":"ㄩㄢ","ün":"ㄩㄣ","ue":"ㄩㄝ","uan2":"ㄩㄢ"}
TONE_MARK = {1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ", 5: "˙"}


def zhuyin_syllable(py):
    m = re.match(r"^([A-Za-zü:]+)([0-5])?$", py)
    if not m:
        return ""
    body = m.group(1).replace("u:", "ü").replace("v", "ü").lower()
    tone = int(m.group(2) or 1)

    # y / w 拼寫還原
    if body.startswith("y"):
        rest = body[1:]
        if rest == "":
            body = "i"
        elif rest.startswith("u"):
            body = "ü" + rest[1:]
        elif rest in ("ong",):
            body = "iong"
        else:
            body = "i" + rest
    elif body.startswith("w"):
        rest = body[1:]
        body = "u" + rest if rest else "u"

    ini = ""
    for k, v in INITIALS:
        if body.startswith(k):
            ini = v
            body = body[len(k):]
            break

    if body == "":
        fin = ""
    elif body in ("i", "u", "ü") and ini in ("ㄓ", "ㄔ", "ㄕ", "ㄖ", "ㄗ", "ㄘ", "ㄙ"):
        fin = ""
    else:
        fin = FINALS.get(body, "")

    mark = TONE_MARK.get(tone, "")
    if tone == 5:
        return "˙" + ini + fin
    return ini + fin + mark


def zhuyin_display(py):
    parts = [zhuyin_syllable(x) for x in py.split()]
    return " ".join(p for p in parts if p)

# ---------- Vietnamese -> Nôm ----------
vi_nom = {}
entries = json.load(open(ROOT / "data" / "entries_raw.json", encoding="utf-8"))
for e in entries:
    vi_nom.setdefault(e["vi"].lower(), e["nom"])

CLS = re.compile(r"LT:.*$")
SLANG = re.compile(r"^\((tiếng lóng|từ lóng|khẩu ngữ|văn học|cũ|đph|phương ngữ)\)", re.I)
SURNAME = re.compile(r"^họ\s*\[", re.I)


ARCHAIC = re.compile(r"\((cổ đại|cổ|archaic|hiếm|ít dùng)\)", re.I)
VARIANT = re.compile(r"biến thể|variant of|cách viết cũ|phiên bản cũ|phiên âm khác", re.I)
NOTE = re.compile(r"^(dùng trong|lượng từ|xem |cũng viết|viết tắt|biến thể của|cách viết khác)", re.I)


# 少數常見字的人工校正（來源資料錯讀）
HV_FIX = {"你": "nhĩ", "打": "đả", "喝": "hát", "切": "thiết", "刺": "thích",
          "看": "khán", "背": "bối", "数": "số", "在": "tại", "里": "lý", "云": "vân"}


def sense_rank(s):
    if SURNAME.match(s):
        return 3
    if SLANG.match(s):
        return 2
    return 1


def clean_sense(s):
    s = CLS.sub("", s).strip()
    s = re.sub(r"\s*\([^()]*\)\s*$", "", s)
    s = s.strip(" ;,.")
    s = re.sub(r"^\([^)]*\)\s*", "", s).strip(" ;,.")
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

    senses = []
    for x in gloss.split("/"):
        if ARCHAIC.search(x) or VARIANT.search(x):
            continue
        c = clean_sense(x)
        if c and not c.lower().startswith("lt:"):
            senses.append(c)
    if not senses:
        continue

    rec = merged.setdefault(simp, {"simp": simp, "trads": [], "py": py, "lines": []})
    if trad not in rec["trads"]:
        rec["trads"].append(trad)
    rec["lines"].append((py, senses))

rows = []
for simp, e in merged.items():
    trads = e["trads"]
    trad = simp if simp in trads else trads[0]

    lines = e["lines"]
    lines.sort(key=lambda l: sense_rank(l[1][0]) if l[1] else 9)
    if len(simp) == 1:
        # 取義項最多的讀音（通常即常用音）
        lines.sort(key=lambda l: -len(l[1]))
        py = lines[0][0]
        lines = [l for l in lines if l[0] == py]
    else:
        # 多字詞：取出現次數最多的讀音
        cnt = {}
        for l in lines:
            cnt[l[0]] = cnt.get(l[0], 0) + 1
        py = max(cnt.items(), key=lambda kv: kv[1])[0]
        lines = [l for l in lines if l[0] == py]
    senses = []
    for l in lines:
        for x in l[1]:
            if x not in senses:
                senses.append(x)
    def prim(s):
        return s.split(";")[0].strip()
    senses = sorted(senses, key=lambda s: (sense_rank(s), len(prim(s).split())))
    pys = py.split()
    hanviet = ""
    if len(pys) == len(simp):
        rs = []
        for ch, p in zip(simp, pys):
            tr = to_trad(ch)
            r = (HV_FIX.get(ch)
                 or hv.get((ch, p)) or hv.get((tr, p))
                 or hv.get((ch, "*")) or hv.get((tr, "*"))
                 or (KVIET.get(ch) or "").split(" ")[0]
                 or (KVIET.get(tr) or "").split(" ")[0])
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
