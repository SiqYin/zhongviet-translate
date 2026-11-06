#!/usr/bin/env python3
"""词条增强：自然越南语对应 + 双语例句（一次过）。

逐批调用 Index-Translate，结果写入 data/enrich_cache.jsonl，可中断续跑。
用法：
    python tools/ai_enrich.py --limit 200          # 试跑
    python tools/ai_enrich.py                      # 全量
    python tools/ai_enrich.py --workers 6
"""
import argparse
import json
import pathlib
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "zhvi_src.json"
CACHE = ROOT / "data" / "enrich_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[㐀-䶿一-鿿]")
_locks = threading.Lock()


def load_words():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    seen, allw = set(), []
    for e in src:
        s = e.get("s") or ""
        if s and s not in seen and CJK.search(s):
            seen.add(s)
            allw.append(s)

    # 常用词優先：HSK 全級 → 單字 → 其餘
    hsk = ROOT / "data" / "hsk_all.tsv"
    hskw = []
    if hsk.exists():
        for line in hsk.read_text(encoding="utf-8-sig").splitlines():
            p = line.split("\t")
            for x in p[:2]:
                x = x.strip()
                if x:
                    hskw.append(x)

    ordered, seen2 = [], set()
    for w in hskw + [x for x in allw if len(x) == 1] + allw:
        if w in seen and w not in seen2:
            seen2.add(w)
            ordered.append(w)
    return ordered


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
            if d.get("w") and isinstance(d.get("v"), list) and len(d["v"]) >= 3:
                cache[d["w"]] = d["v"]
    return cache


def post(prompt, timeout=200):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.25,
        "max_tokens": 6000,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY",
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"]


def build_prompt(words):
    payload = {w: "" for w in words}
    return (
        "请处理下面每个中文词条，输出 JSON 对象，key 原样保留，value 是长度为 3 的数组 [A, B, C]：\n"
        "A = 该词最自然、最常用的越南语对应（词语或短语，禁止逐字直译，专有名词用通行译名）；\n"
        "B = 一个简短自然的中文例句（8~20 字，必须是纯中文句子且包含该词；词条若是谚语则体现使用语境）；\n"
        "C = B 的越南语译文（必须是纯越南语，地道自然，禁止逐字直译）。\n"
        "示例：输入 {\"鸡\":\"\"} → 输出 {\"鸡\":[\"gà\",\"妈妈炖了一锅鸡汤。\",\"Mẹ nấu một nồi canh gà.\"]}\n"
        "注意：B 只能写中文，C 只能写越南语。只输出 JSON，无任何多余文字。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def parse_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        return {}
    try:
        return json.loads(text[i:j + 1])
    except Exception:
        return {}


def valid(word, val):
    """返回 [term, zh_ex, vi_ex] 或 None。"""
    if not (isinstance(val, list) and len(val) >= 3):
        return None
    a, b, c = (str(x).strip() for x in val[:3])
    # A：越南语词/短语
    if not a or CJK.search(a) or len(a) > 40 or len(a.split()) > 5:
        return None
    if a.lower() == word.lower():
        return None
    # B：中文例句，须含该词（简繁任一）
    if not b or not CJK.search(b) or len(b) < 5 or len(b) > 60:
        return None
    if word not in b:
        return None
    # C：越南语译文，不得含汉字
    if not c or CJK.search(c) or len(c) > 120 or len(c.split()) > 25:
        return None
    return [a, b, c]


def worker(q, cache, lock, done, total, stop):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        if stop.is_set():
            return
        prompt = build_prompt(batch)
        got = {}
        for attempt in range(4):
            try:
                txt = post(prompt)
                got = parse_json(txt)
                if not any(isinstance(v, list) and len(v) >= 3 for v in got.values()):
                    raise ValueError("empty/malformed batch")
                break
            except Exception as e:
                got = {}
                if attempt == 3:
                    with lock:
                        print("  ! batch failed:", batch[0], e, flush=True)
                time.sleep(3 * (attempt + 1))
        with lock:
            n_ok = 0
            for w in batch:
                v = valid(w, got.get(w, ""))
                if v:
                    cache[w] = v
                    with CACHE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
                    n_ok += 1
            done[0] += len(batch)
            ok[0] += n_ok
            print("  %d/%d (ok %d)  %s" % (done[0], total, ok[0], batch[0]), flush=True)
        time.sleep(0.3)


ok = [0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    words = load_words()
    cache = load_cache()
    todo = [w for w in words if w not in cache]
    if args.limit:
        todo = todo[:args.limit]

    total = len(todo)
    print("待增强 %d 條（已快取 %d）" % (total, len(cache)), flush=True)
    if not total:
        return

    q = queue.Queue()
    for i in range(0, total, args.batch):
        q.put(todo[i:i + args.batch])

    lock = threading.Lock()
    done = [0]
    stop = threading.Event()
    threads = [threading.Thread(target=worker, args=(q, cache, lock, done, total, stop), daemon=True)
               for _ in range(args.workers)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("完成 %d 條（有效 %d），耗時 %.0fs，快取共 %d" % (done[0], ok[0], time.time() - t0, len(cache)), flush=True)


if __name__ == "__main__":
    main()
