#!/usr/bin/env python3
"""Build the Chinese -> Vietnamese dictionary from CVDICT (CC BY-SA 4.0)."""
import json, re, csv, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "cvdict.u8"

# ---------- Hán-Việt readings ----------
hv = {}
ALLR = {}                      # 字 -> 該字在詞表中出現過的全部漢越音（保序）
for row in csv.reader(open(ROOT.parent / "hanviet.csv", encoding="utf-8")):
    if not row or row[0] == "char":
        continue
    ch, vals, py = row[0], row[1], row[2]
    lst = re.findall(r"'([^']*)'", vals)
    if not lst:
        continue
    hv[(ch, py)] = lst[0]
    hv.setdefault((ch, "*"), lst[0])
    bucket = ALLR.setdefault(ch, [])
    for m in lst:
        if m and m not in bucket:
            bucket.append(m)

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
    out = re.sub(r"\s+r(?=$|\s)", "r", out)      # 兒化：zuó r -> zuór
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
          "看": "khán", "背": "bối", "数": "số", "在": "tại", "里": "lý", "云": "vân",
          "侗": "đồng"}


def read_of(ch, p):
    """單個音節的漢越音：先查人工校正，再查按拼音對齊的詞表，最後退到 Unihan。"""
    tr = to_trad(ch)
    return (HV_FIX.get(ch)
            or hv.get((ch, p)) or hv.get((tr, p))
            or hv.get((ch, "*")) or hv.get((tr, "*"))
            or (KVIET.get(ch) or "").split(" ")[0]
            or (KVIET.get(tr) or "").split(" ")[0]
            or "")


def read_of_nofix(ch, p):
    """不含人工校正的取音（用來把被校正掉的舊值排除出列表）。"""
    tr = to_trad(ch)
    return (hv.get((ch, p)) or hv.get((tr, p))
            or hv.get((ch, "*")) or hv.get((tr, "*"))
            or (KVIET.get(ch) or "").split(" ")[0]
            or (KVIET.get(tr) or "").split(" ")[0]
            or "")


def all_readings(ch, prim, py):
    """該字的全部漢越音：主讀音在前，其餘按複音詞出現頻率排序。"""
    tr = to_trad(ch)
    pool = []
    seen = set()
    for src_ch in (ch, tr):
        for r in ALLR.get(src_ch, []):
            k = r.lower()
            if k not in seen:
                seen.add(k)
                pool.append(r)
    drop = ""
    if HV_FIX.get(ch):
        drop = read_of_nofix(ch, py).lower()      # 被人工校正取代的舊值
    out, taken = [], set()
    if prim:
        out.append(prim)
        taken.add(prim.lower())
    freq = READ_CNT.get(ch) or READ_CNT.get(tr) or {}
    pool.sort(key=lambda r: -freq.get(r.lower(), 0))
    for r in pool:
        k = r.lower()
        if k in taken or (drop and k == drop):
            continue
        taken.add(k)
        out.append(r)
    if not out:
        out = [x for x in (KVIET.get(ch) or KVIET.get(tr) or "").split(" ") if x]
    return out


CSV_ROWS = {}
for _k in hv:
    if _k[1] != "*":
        CSV_ROWS.setdefault(_k[0], set()).add(_k[1])


def read_src(ch, p):
    tr = to_trad(ch)
    if HV_FIX.get(ch):
        return "fix"
    if (ch, p) in hv or (tr, p) in hv:
        return "exact"
    if len(CSV_ROWS.get(ch) or CSV_ROWS.get(tr) or ()) > 1:
        return "star-multi"
    if (ch, "*") in hv or (tr, "*") in hv:
        return "star"
    if KVIET.get(ch) or KVIET.get(tr):
        return "unihan"
    return "none"


def sense_rank(s):
    if SURNAME.match(s):
        return 3
    if SLANG.match(s):
        return 2
    return 1


EMPTY_SENSE = re.compile(r"^(đọc là|cũng đọc là|cũng như|viết là|tức là|hay là)$", re.I)


def clean_sense(s):
    s = CLS.sub("", s).strip()
    s = re.sub(r"\[[^\]]*\]", " ", s)            # 去掉 CC-CEDICT 的 [pin1 yin1] 殘留
    s = re.sub(r"\s*\([^()]*\)\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ;,.")
    s = re.sub(r"^\([^)]*\)\s*", "", s).strip(" ;,.")
    if NOTE.match(s) or EMPTY_SENSE.match(s):
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
        # 先去掉括號說明，避免把括號內容從中間拆斷
        clean = re.sub(r"\([^()]*\)", " ", x)
        for part in clean.split(";"):         # 一個義項裡擠了多個近義詞，拆開
            c = clean_sense(part)
            if c and not c.lower().startswith("lt:") and "~" not in c:
                senses.append(c)
    if not senses:
        continue

    rec = merged.setdefault(simp, {"simp": simp, "trads": [], "py": py, "lines": []})
    if trad not in rec["trads"]:
        rec["trads"].append(trad)
    rec["lines"].append((py, senses))

# 用詞典自身的複音詞統計，決定每個單字的主讀音
READ_CNT = {}
for _simp, _e in merged.items():
    if len(_simp) < 2:
        continue
    for _py, _ in _e["lines"]:
        _pys = _py.split()
        if len(_pys) != len(_simp):
            continue
        for _ch, _p in zip(_simp, _pys):
            _r = read_of(_ch, _p)
            if not _r:
                continue
            _d = READ_CNT.setdefault(_ch, {})
            _k = _r.lower()
            _d[_k] = _d.get(_k, 0) + 1

PRIMARY = {}
for _ch, _d in READ_CNT.items():
    _items = sorted(_d.items(), key=lambda kv: -kv[1])
    if len(_items) < 2:
        continue
    _top, _n1 = _items[0]
    _n2 = _items[1][1]
    if _n1 >= 3 and _n1 >= 1.3 * max(_n2, 1):
        PRIMARY[_ch] = _top

HV_CHANGED = []
HV_SUSPECT = []

rows = []
src_dump = []

# AI 校正結果（word -> 越南語對應詞），不存在就跳過
AI_FIX = {}
_fix_path = ROOT / "data" / "ai_fix.json"
if _fix_path.exists():
    AI_FIX = json.loads(_fix_path.read_text(encoding="utf-8"))
    print("ai_fix entries", len(AI_FIX))

for simp, e in merged.items():
    trads = e["trads"]
    trad = simp if simp in trads else trads[0]

    lines = e["lines"]
    lines.sort(key=lambda l: sense_rank(l[1][0]) if l[1] else 9)
    if len(simp) == 1:
        # 先看複音詞統計給出的主讀音，沒有才退回「義項最多的讀音」
        want = PRIMARY.get(simp)
        chosen = None
        if want:
            cand = [l for l in lines
                    if len(l[0].split()) == 1 and read_of(simp, l[0]).lower() == want]
            if cand:
                cand.sort(key=lambda l: -len(l[1]))
                chosen = cand[0][0]
        if chosen is None:
            lines.sort(key=lambda l: -len(l[1]))
            chosen = lines[0][0]
        else:
            old = max(lines, key=lambda l: len(l[1]))[0]
            if old != chosen:
                HV_CHANGED.append([simp, old, chosen, read_of(simp, old), want])
        py = chosen
        _src = read_src(simp, py)
        if _src in ("star-multi", "unihan", "none", "star"):
            HV_SUSPECT.append([simp, py, read_of(simp, py), _src])
    else:
        # 多字詞：取出現次數最多的讀音
        cnt = {}
        for l in lines:
            cnt[l[0]] = cnt.get(l[0], 0) + 1
        py = max(cnt.items(), key=lambda kv: kv[1])[0]

    # 主讀音的義項排前面，其餘讀音的義項保留在後（避免整條意思被丟掉）
    main_lines = [l for l in lines if l[0] == py]
    other_lines = [l for l in lines if l[0] != py]
    ordered = main_lines + other_lines

    senses = []
    for l in ordered:
        for x in l[1]:
            if x not in senses:
                senses.append(x)
    def prim(s):
        return s.split(";")[0].strip()
    senses = sorted(senses, key=lambda s: (sense_rank(s), len(prim(s).split())))
    # 去掉括號後「họ [Leng3]」變成裸的 "họ"，會被誤當主義，排到最後
    if len(senses) > 1:
        bare = [s for s in senses if s.strip().lower() == "họ"]
        if bare:
            senses = [s for s in senses if s.strip().lower() != "họ"] + bare
    senses_orig = senses[:]          # 校正前，供比對與外部工具使用

    # AI 校正：把模型給的最常用對應詞提到第一位
    fix = AI_FIX.get(simp) or AI_FIX.get(trad) or ""
    fix = fix.strip()
    if fix:
        fl = fix.lower()
        senses = [s for s in senses if s.lower().strip() != fl]
        senses.insert(0, fix)
        senses = senses[:5]

    pys = py.split()
    hanviet = ""
    if len(pys) == len(simp):
        if len(simp) == 1:
            rs = all_readings(simp, read_of(simp, pys[0]), pys[0])
            if rs:
                hanviet = "、".join(rs)
        else:
            rs = [read_of(ch, p) for ch, p in zip(simp, pys)]
            if all(rs):
                hanviet = " ".join(rs)

    nom = ""
    for s in senses:
        key = s.lower()
        if key in vi_nom:
            nom = vi_nom[key]
            break

    rows.append([trad, simp, pinyin_display(py), "；".join(senses[:5]), hanviet, nom])
    src_dump.append({"s": simp, "t": trad, "y": pinyin_display(py),
                     "g": senses_orig[:5], "h": hanviet})

(ROOT / "data" / "zhvi_src.json").write_text(
    json.dumps(src_dump, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

rows.sort(key=lambda r: (len(r[1]), r[1]))
payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
(ROOT / "app").mkdir(exist_ok=True)
(ROOT / "app" / "zhvi.js").write_text("window.ZV=" + payload + ";\n", encoding="utf-8")

(ROOT / "data" / "hv_primary.json").write_text(
    json.dumps(PRIMARY, ensure_ascii=False, indent=0), encoding="utf-8")
HV_CHANGED.sort(key=lambda r: r[0])
with open(ROOT / "data" / "hv_fix_report.tsv", "w", encoding="utf-8") as f:
    f.write("字\t原拼音\t新拼音\t原漢越音\t新漢越音\n")
    for r in HV_CHANGED:
        f.write("\t".join(r) + "\n")

print("entries", len(rows))
with open(ROOT / "data" / "hv_suspect.tsv", "w", encoding="utf-8") as f:
    f.write("字\t拼音\t漢越音\t來源\n")
    for r in sorted(HV_SUSPECT):
        f.write("\t".join(r) + "\n")

print("hanviet primary changed", len(HV_CHANGED))
print("hanviet suspect", len(HV_SUSPECT))
print("with hanviet", sum(1 for r in rows if r[4]))
print("with nom", sum(1 for r in rows if r[5]))
print("size MB %.1f" % (len(payload.encode()) / 1024 / 1024))
