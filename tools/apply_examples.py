#!/usr/bin/env python3
"""把重写好的例句写回 app/zhvi.js。

只替换 data/ex_flag_ids.json 里列出的、且中越两句都齐全的条目。

    python tools/apply_examples.py [--dry]
"""
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
FLAG = ROOT / "data" / "ex_flag_ids.json"
ZH = ROOT / "data" / "ex_new_zh.jsonl"
VI = ROOT / "data" / "ex_new_vi.jsonl"


def load_jsonl(p):
    d = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if "i" in o:
                d[o["i"]] = o
    return d


def main():
    dry = "--dry" in sys.argv
    raw = SRC.read_bytes().decode("utf-8")
    i, j = raw.find("["), raw.rfind("]")
    head, ZV, tail = raw[:i], json.loads(raw[i:j + 1]), raw[j + 1:]

    ids = set(json.loads(FLAG.read_text(encoding="utf-8"))) if FLAG.exists() else set()
    zh = load_jsonl(ZH)
    vi = load_jsonl(VI)

    applied = skipped = 0
    for k in ids:
        a, b = zh.get(k), vi.get(k)
        if not a or not b:
            skipped += 1
            continue
        s1, s2 = a.get("zh", ""), b.get("vi", "")
        e = ZV[k]
        if not s1 or not s2 or e[1] not in s1:
            skipped += 1
            continue
        e[6] = [s1, s2]
        applied += 1

    print("重写写回 %d 条，跳过 %d 条（缺中文或越南语）" % (applied, skipped))
    if dry:
        return
    out = head + json.dumps(ZV, ensure_ascii=False, separators=(",", ":")) + tail
    SRC.write_bytes(out.encode("utf-8"))
    print("已写入 %s（%.1f MB）" % (SRC.name, len(out.encode("utf-8")) / 1048576))


if __name__ == "__main__":
    main()
