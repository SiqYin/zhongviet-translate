#!/usr/bin/env python3
"""清理过期翻译：ex_vi_cache 里译文对应的中文例句已被病句筛修改过的，删掉该行待重翻。

用法：python tools/prune_stale_vi.py   （跑完后再执行 ai_examples --phase vi）
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
VI_CACHE = ROOT / "data" / "ex_vi_cache.jsonl"
FIX_CACHE = ROOT / "data" / "ex_fix_cache.jsonl"


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

    if not VI_CACHE.exists():
        print("no vi cache")
        return

    lines = [l for l in VI_CACHE.read_text(encoding="utf-8").splitlines() if l.strip()]
    keep, drop = [], 0
    for l in lines:
        try:
            d = json.loads(l)
        except Exception:
            continue
        w = d.get("w")
        v = d.get("v")
        stale = (w in fixes and isinstance(v, list) and len(v) >= 2 and v[0] != fixes[w])
        if stale:
            drop += 1
            continue
        keep.append(l)
    VI_CACHE.write_text("".join(x + "\n" for x in keep), encoding="utf-8")
    print("vi cache: kept %d, dropped %d stale" % (len(keep), drop))


if __name__ == "__main__":
    main()
