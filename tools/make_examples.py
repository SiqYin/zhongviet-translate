#!/usr/bin/env python3
"""把 ex_vi_cache.jsonl 的双语例句合并为 data/examples.json（word -> [zh, vi]）。

只收两段都合格的条目。用法：python tools/make_examples.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
VI_CACHE = ROOT / "data" / "ex_vi_cache.jsonl"
VI_FALLBACK = ROOT / "data" / "ex_vi_cache_2b.jsonl"
FIX_CACHE = ROOT / "data" / "ex_fix_cache.jsonl"
OUT = ROOT / "data" / "examples.json"

CJK = re.compile(r"[㐀-䶿一-鿿]")


def main():
    fixes = {}
    if FIX_CACHE.exists():
        for line in FIX_CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("w") and isinstance(d.get("v"), str) and d["v"]:
                fixes[d["w"]] = d["v"]

    out = {}
    n = 0
    nfix = 0
    # 2B 旧譯先打底，35B 新譯覆蓋
    merged = {}
    for path in (VI_FALLBACK, VI_CACHE):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            w, v = d.get("w"), d.get("v")
            if w and isinstance(v, list) and len(v) >= 2:
                merged[w] = v
    for w, v in merged.items():
            zh, vi = str(v[0]).strip(), str(v[1]).strip()
            if w in fixes:
                zh = fixes[w]
                nfix += 1
            if not zh or not vi or not CJK.search(zh) or CJK.search(vi):
                continue
            if w not in zh:
                # 与 ai_examples.valid_zh 一致：離合詞拆開也算（請了一天假）
                it = iter(zh)
                if not all(ch in it for ch in w):
                    continue
            out[w] = [zh, vi]
            n += 1
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("examples.json：%d 條（含修正 %d）" % (n, nfix))


if __name__ == "__main__":
    main()
