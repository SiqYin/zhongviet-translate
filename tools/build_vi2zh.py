#!/usr/bin/env python3
"""構建越南語 -> 中文對照表 app/vi2zh.js。

優先級：
1. data/vi_func_words.tsv（虛詞定稿表）——虛詞一律以人工定稿為準；
2. AI 直譯快取（data/vi_gloss_cache.jsonl，tools/ai_vi_gloss.py 產出）；
3. 啟發式兜底（義項位置靠前 > 二字詞 > 有字喃/漢越音），優先取現代常用詞頭。

    python tools/build_vi2zh.py
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
CACHE = ROOT / "data" / "vi_gloss_cache.jsonl"
MODERN = ROOT / "data" / "modern_chinese_words.tsv"
FUNC = ROOT / "data" / "vi_func_words.tsv"
OUT = ROOT / "app" / "vi2zh.js"

MAX_SYL = 4
MAX_GLOSS = 4

MODERN_RANK = {}
for _row in csv.DictReader(MODERN.open(encoding="utf-8"), delimiter="\t"):
    _w = (_row.get("词语") or "").strip()
    if not _w:
        continue
    try:
        _r = int(_row.get("频序号") or 99999)
    except Exception:
        _r = 99999
    if _w not in MODERN_RANK or _r < MODERN_RANK[_w]:
        MODERN_RANK[_w] = _r


def norm(s):
    s = re.sub(r"[（(][^）)]*[）)]", " ", (s or "").lower())
    s = re.sub(r"[.,;:!?\u201d\u2019\]\[]+$", "", s).strip()
    return re.sub(r"\s+", " ", s)


def load_func():
    d = {}
    if FUNC.exists():
        for line in FUNC.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            w = parts[0].strip()
            g = [x.strip() for x in parts[1].split("；") if x.strip()]
            if w and g:
                d[norm(w)] = g
    return d


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
            if isinstance(d.get("v"), list) and d.get("w") and d["v"]:
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
    func = load_func()

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

    out = {}
    n_func = n_ai = n_fb = 0
    for phrase, d in cand.items():
        if phrase in func:
            out[phrase] = func[phrase][:MAX_GLOSS]
            n_func += 1
            continue
        g = cache.get(phrase)
        if g:
            out[phrase] = g[:MAX_GLOSS]
            n_ai += 1
            continue
        cands = [(zh, e[2], j, e) for zh, (j, e) in d.items()]
        order = heur_rank(cands)
        modern = [z for z in order if z in MODERN_RANK]
        out[phrase] = (modern or order)[:2]
        n_fb += 1

    # 虛詞定稿表裡的詞即使不在候選池裡也要有條目，保證虛詞全覆蓋
    for w, g in func.items():
        if w not in out:
            out[w] = g[:MAX_GLOSS]
            n_func += 1

    js = "window.VI2ZH=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";"
    OUT.write_text(js, encoding="utf-8")
    print("詞條 %d（虛詞定稿 %d / AI 直譯 %d / 啟發式兜底 %d）-> %s（%.1f MB）" %
          (len(out), n_func, n_ai, n_fb, OUT.name, len(js.encode("utf-8")) / 1048576))


if __name__ == "__main__":
    main()
