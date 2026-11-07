#!/usr/bin/env python3
"""構建越南語 -> 中文對照表 app/vi2zh.js。

把詞庫全部義項（1-4 音節）反演成「越南語詞 -> 候選中文詞」，其中：
- 有 AI 精排快取（data/ai_vi2zh_cache.jsonl，tools/ai_vi2zh.py 產出）的用 AI 排序；
- 其餘用啟發式排序（義項位置靠前 > 二字詞 > 有字喃/漢越音）。
只輸出「候選 >= 2 或 AI 參與過」的詞：單候選詞運行時掃描即可得出，
無需重複存一份（保持檔案精簡）。

    python tools/build_vi2zh.py
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
CACHE = ROOT / "data" / "ai_vi2zh_cache.jsonl"
OUT = ROOT / "app" / "vi2zh.js"

MAX_SYL = 4


def norm(s):
    s = re.sub(r"[（(][^）)]*[）)]", " ", (s or "").lower())
    s = re.sub(r"[.,;:!?\u201d\u2019\]\[]+$", "", s).strip()
    return re.sub(r"\s+", " ", s)


def load_zv():
    src = SRC.read_text(encoding="utf-8")
    m = re.search(r"window\.ZV=(\[.*?\]);?\s*$", src, re.S)
    return json.loads(m.group(1))


def load_cache():
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if isinstance(d.get("v"), list) and d.get("w"):
                cache[d["w"]] = d["v"]
    return cache


def heur_rank(cands):
    """啟發式排序：義項位置 > 詞長（2字詞優先）> 有字喃 > 有漢越音。"""
    def key(c):
        zh, py, j, e = c
        L = len(zh)
        s = j * 10
        s += 0 if L == 2 else (4 if L == 3 else (8 if L == 1 else 6))
        if e[5]:
            s -= 1
        if not e[4]:
            s += 1
        return (s, L, zh)

    return [c[0] for c in sorted(cands, key=key)]


def main():
    ZV = load_zv()
    cache = load_cache()

    cand = {}
    for e in ZV:
        zh = e[1]
        for j, raw in enumerate((e[3] or "").split("；")):
            s = norm(raw)
            if not s:
                continue
            sy = s.split()
            if 1 <= len(sy) <= MAX_SYL:
                cand.setdefault(s, {}).setdefault(zh, (j, e))

    ai_used = 0
    out = {}
    for phrase, d in cand.items():
        cands = [(zh, e[2], j, e) for zh, (j, e) in d.items()]
        order = None
        if len(cands) >= 2:
            if phrase in cache:
                ai = [z for z in cache[phrase] if z in d]
                if ai:
                    rest = [c[0] for c in sorted(cands, key=lambda c: c[2]) if c[0] not in ai]
                    order = (ai + rest)[:4]
                    ai_used += 1
                else:
                    order = heur_rank(cands)[:4]     # AI 判定候選全垃圾：啟發式兜底
            else:
                order = heur_rank(cands)[:4]
        if order:
            out[phrase] = order

    js = "window.VI2ZH=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";"
    OUT.write_text(js, encoding="utf-8")
    print("詞條 %d（AI 精排 %d）-> %s（%.1f MB）" %
          (len(out), ai_used, OUT.name, len(js.encode("utf-8")) / 1048576))


if __name__ == "__main__":
    main()
