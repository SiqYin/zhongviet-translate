#!/usr/bin/env python3
"""把中文虚词定稿表写进 app/zhvi.js，并整理例句。

1. data/zh_func_words.tsv：中文虚词 -> 越南语释义（；分隔，有序）。
   已有词条整条替换义项（虚词的旧义项多半是「拿常用字硬凑」或带长解释），
   缺的补建词条（拼音列可留空）。
2. 例句整理（每词一条 [中文句, 越南语句]）：
   - 中文句不含词头 -> 删
   - 「读作 / 古籍 / 这个字」这类元例句 -> 删
   - 单字词头是生僻字或文言虚词 -> 删
   - 双字词头不在现代常用词表、且含文言虚词 -> 删（若然/信然/倘然/恁般一类）
   - 例句里出现若然/信然/倘然/恁般等文言词 -> 删

    python tools/apply_func_words.py [--dry]
"""
import csv
import json
import pathlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "zhvi.js"
TABLE = ROOT / "data" / "zh_func_words.tsv"
MODERN = ROOT / "data" / "modern_chinese_words.tsv"

CLASSIC_SINGLE = set("咁偌恁焉矣哉兮欤耶汝吾予曰云盖恁")
CLASSIC_CHARS = set("若然倘恁般乃焉矣哉兮之乎者也而其则此彼何莫曰云盖")
BAD_ARCHAIC = ("若然", "信然", "倘然", "恁般", "恁么", "这般", "那般", "之乎者也")
META = ("读作", "古籍", "这个字", "該字", "该字", "念作", "音读")

MODERN_RANK = set()
COMMON_CHARS = set()
for row in csv.DictReader(MODERN.open(encoding="utf-8"), delimiter="\t"):
    w = (row.get("词语") or "").strip()
    if not w:
        continue
    MODERN_RANK.add(w)
    COMMON_CHARS.update(w)


def load():
    raw = SRC.read_bytes().decode("utf-8")
    i, j = raw.find("["), raw.rfind("]")
    return raw[:i], json.loads(raw[i:j + 1]), raw[j + 1:]


def main():
    dry = "--dry" in sys.argv
    head, ZV, tail = load()

    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        w = parts[0].strip()
        senses = [x.strip() for x in parts[1].split("；") if x.strip()]
        py = parts[2].strip() if len(parts) > 2 else ""
        if w and senses:
            rows.append((w, senses, py))

    idx = {}
    for k, e in enumerate(ZV):
        idx.setdefault(e[1], []).append(k)

    replaced = added = 0
    for w, senses, py in rows:
        s = "；".join(senses)
        if w in idx:
            for k in idx[w]:
                ZV[k][3] = s
            replaced += 1
        else:
            ZV.append([w, w, py, s, "", "", ""])
            idx[w] = [len(ZV) - 1]
            added += 1

    dropped = {"no_head": 0, "meta": 0, "single": 0, "classical2": 0, "archaic": 0}
    kept = 0
    for e in ZV:
        ex = e[6]
        if not ex:
            continue
        if not (isinstance(ex, list) and len(ex) == 2 and isinstance(ex[0], str) and isinstance(ex[1], str)):
            e[6] = ""
            dropped["meta"] += 1
            continue
        zh, hw = ex[0], e[1]
        if hw not in zh:
            e[6] = ""
            dropped["no_head"] += 1
            continue
        if any(m in zh for m in META):
            e[6] = ""
            dropped["meta"] += 1
            continue
        if len(hw) == 1 and (hw in CLASSIC_SINGLE or hw not in COMMON_CHARS):
            e[6] = ""
            dropped["single"] += 1
            continue
        if len(hw) == 2 and hw not in MODERN_RANK and any(ch in CLASSIC_CHARS for ch in hw):
            e[6] = ""
            dropped["classical2"] += 1
            continue
        if any(b in zh and b != hw for b in BAD_ARCHAIC):
            e[6] = ""
            dropped["archaic"] += 1
            continue
        kept += 1

    print("虚词替换 %d 条，新建 %d 条；例句保留 %d，删除 %s" % (replaced, added, kept, dropped))
    if dry:
        return
    out = head + json.dumps(ZV, ensure_ascii=False, separators=(",", ":")) + tail
    SRC.write_bytes(out.encode("utf-8"))
    print("已写入 %s（%.1f MB）" % (SRC.name, len(out.encode("utf-8")) / 1048576))


if __name__ == "__main__":
    main()
