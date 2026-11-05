#!/usr/bin/env python3
"""把 ai_cache.jsonl 轉成 data/ai_fix.json（word -> 首選越南語詞），並輸出審閱報告。"""
import json
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "ai_cache.jsonl"
SRC = ROOT / "data" / "zhvi_src.json"
FIX = ROOT / "data" / "ai_fix.json"
REPORT = ROOT / "data" / "ai_fix_report.tsv"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
NOTE = re.compile(r"^(họ\s*\[|biến thể|cách viết|xem |cũng viết|viết tắt|dùng trong|lượng từ)", re.I)


def is_rare(w):
    """CJK 擴展區的字，模型多半只能靠字形瞎猜，不做校正。"""
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

    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("w") and d.get("v"):
                cache[d["w"]] = d["v"]

    fix, rows = {}, []
    stats = Counter()
    for w, v in cache.items():
        e = entries.get(w)
        if not e:
            stats["無此詞條"] += 1
            continue
        cur = e["g"][0] if e["g"] else ""
        if CJK.search(v) or len(v) > 40 or len(v.split()) > 5:
            stats["值不合格"] += 1
            continue
        if norm(cur) == norm(v):
            stats["一致"] += 1
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
        hv = (e.get("h") or "").lower().split()
        if len(w) == 1 and hv and norm(v) in [x.lower() for x in hv]:
            stats["值是漢越音(略過)"] += 1
            continue

        # 舊值可疑程度
        bad = bool(NOTE.match(cur) or "(" in cur or "（" in cur or len(cur) > 26)
        kind = "修正錯義" if bad else ("同義替換" if len(norm(cur).split()) <= 5 else "收窄首義")
        stats[kind] += 1
        fix[w] = v
        rows.append((kind, w, e["y"], cur, v, e["t"]))

    FIX.write_text(json.dumps(fix, ensure_ascii=False, indent=0), encoding="utf-8")

    rows.sort(key=lambda r: (r[0] != "修正錯義", r[1]))
    with REPORT.open("w", encoding="utf-8") as f:
        f.write("類型\t詞\t拼音\t原首義\tAI校正\t繁體\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ") for x in r) + "\n")

    print("快取 %d 條" % len(cache))
    for k, v in stats.most_common():
        print("  %-6s %d" % (k, v))
    print("寫入 ai_fix.json：%d 條" % len(fix))
    print("報告：data/ai_fix_report.tsv")


if __name__ == "__main__":
    main()
