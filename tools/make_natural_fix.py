#!/usr/bin/env python3
"""把 natural_cache.jsonl 的判改结果合入 data/ai_fix.json，并输出审閱报告。

- v == "" 表示保留原值，跳过
- 与 make_ai_fix.py 同一套守卫：罕见字、姓氏义、专名音译、值是汉越音
用法：python tools/make_natural_fix.py
"""
import json
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "natural_cache.jsonl"
SRC = ROOT / "data" / "zhvi_src.json"
FIX = ROOT / "data" / "ai_fix.json"
REPORT = ROOT / "data" / "natural_fix_report.tsv"

CJK = re.compile(r"[㐀-䶿一-鿿]")


def is_rare(w):
    return any(0x3400 <= ord(c) <= 0x4DBF or ord(c) >= 0x20000 for c in w)


def first_tok(s):
    m = re.match(r"[A-Za-zÀ-ỹ]+", (s or "").strip())
    return m.group(0) if m else ""


def norm(s):
    s = (s or "").lower().strip()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ;,.、")


def main():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    entries = {}
    for e in src:
        entries.setdefault(e["s"], e)
        if e["t"] != e["s"]:
            entries.setdefault(e["t"], e)

    fix = json.loads(FIX.read_text(encoding="utf-8")) if FIX.exists() else {}

    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("w"):
                cache[d["w"]] = d.get("v") or ""

    rows, stats = [], Counter()
    for w, v in cache.items():
        if not v:
            stats["保留原值"] += 1
            continue
        e = entries.get(w)
        if not e:
            stats["無此詞條"] += 1
            continue
        cur = fix.get(w) or (e["g"][0] if e["g"] else "")
        if CJK.search(v) or len(v) > 40 or len(v.split()) > 5:
            stats["值不合格"] += 1
            continue
        if norm(cur) == norm(v):
            stats["一致(略過)"] += 1
            continue
        if norm(v) == norm(w):
            stats["原樣回抄(略過)"] += 1
            continue
        if is_rare(w):
            stats["罕見字(略過)"] += 1
            continue
        if len(w) == 1 and norm(v) == "họ" and any(x.lower().startswith("họ") for x in e["g"]):
            stats["姓氏義(略過)"] += 1
            continue
        _ot, _nt = first_tok(cur), first_tok(v)
        if _ot and _nt and _ot[0].isupper() and _nt[0].isupper() and _ot.lower() != _nt.lower():
            stats["專名音譯(略過)"] += 1
            continue
        hv = [x for x in re.split(r"[\s、,，]+", (e.get("h") or "").lower()) if x]
        if len(w) == 1 and hv and norm(v) in [x.lower() for x in hv]:
            stats["值是漢越音(略過)"] += 1
            continue

        fix[w] = v
        rows.append((w, e["y"], cur, v, e["t"]))
        stats["替換"] += 1

    FIX.write_text(json.dumps(fix, ensure_ascii=False, indent=0), encoding="utf-8")
    rows.sort(key=lambda r: r[0])
    with REPORT.open("w", encoding="utf-8") as f:
        f.write("詞\t拼音\t原首義\t自然化後\t繁體\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ") for x in r) + "\n")

    print("快取 %d 條" % len(cache))
    for k, v in stats.most_common():
        print("  %-6s %d" % (k, v))
    print("ai_fix.json 共 %d 條；報告：%s" % (len(fix), REPORT.name))


if __name__ == "__main__":
    main()
