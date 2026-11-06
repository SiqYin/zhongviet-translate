#!/usr/bin/env python3
"""例句病句筛修：判定中文例句是否自然，不自然的给出修正句。

输出 data/ex_fix_cache.jsonl  {w: 修正后的例句}（自然的记空串 = 不动）。
用法：
    python tools/ai_review.py --limit 100
    python tools/ai_review.py --workers 8
"""
import argparse
import json
import pathlib
import queue
import re
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZH_CACHE = ROOT / "data" / "ex_zh_cache.jsonl"
CACHE = ROOT / "data" / "ex_fix_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[㐀-䶿一-鿿]")
LV = re.compile(r"[A-Za-zÀ-ỹ]")


def load_zh():
    out = {}
    if ZH_CACHE.exists():
        for line in ZH_CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("w") and isinstance(d.get("v"), str):
                out[d["w"]] = d["v"]
    return out


def load_cache():
    done = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("w") is not None:
                done[d["w"]] = d.get("v") or ""
    return done


def post(prompt, timeout=200):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4000,
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


def build_prompt(pairs):
    payload = {w: s for w, s in pairs}
    return (
        "下面 JSON 的每个 key 是中文词，value 是为该词写的中文例句。\n"
        "请检查例句是否语法正确、自然通顺、用词得当。若有语病、生硬或用法错误，"
        "填入修正后的中文例句（8~20 字，包含该词）；若已经自然，填空字符串 \"\"。\n"
        "示例：输入 {\"一语中的\":\"他的一语中的，点明了问题核心。\"} → 输出 {\"一语中的\":\"他的回答一语中的，点明了问题核心。\"}\n"
        "示例：输入 {\"鸡\":\"妈妈炖了一锅鸡汤。\"} → 输出 {\"鸡\":\"\"}\n"
        "key 原样保留。只输出 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def parse_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        return {}
    s = text[i:j + 1]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        return json.loads(s)
    except Exception:
        return {}


def valid(word, val, orig):
    if not isinstance(val, str):
        return None
    v = val.strip()
    if not v:
        return ""                       # 自然，不动
    if not CJK.search(v) or LV.search(v):
        return None
    if word not in v or len(v) < 6 or len(v) > 60:
        return None
    if v == orig:
        return ""
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=25)
    args = ap.parse_args()

    zh = load_zh()
    cache = load_cache()
    todo = [(w, s) for w, s in zh.items() if w not in cache]
    if args.limit:
        todo = todo[:args.limit]
    total = len(todo)
    print("待筛 %d（已筛 %d）" % (total, len(cache)), flush=True)
    if not total:
        return

    q = queue.Queue()
    for i in range(0, total, args.batch):
        q.put(todo[i:i + args.batch])

    lock = threading.Lock()
    done = [0]
    fixed = [0]
    judged = [0]

    def worker():
        while True:
            try:
                b = q.get_nowait()
            except queue.Empty:
                return
            got = {}
            for attempt in range(4):
                try:
                    txt = post(build_prompt(b))
                    got = parse_json(txt)
                    if not any(k in got for k, _ in b):
                        raise ValueError("no keys")
                    break
                except Exception as e:
                    got = {}
                    if attempt == 3:
                        with lock:
                            print("  ! batch failed:", b[0][0], e, flush=True)
                    time.sleep(3 * (attempt + 1))
            with lock:
                for w, orig in b:
                    v = valid(w, got.get(w, ""), orig)
                    if v is None:
                        continue
                    cache[w] = v
                    with CACHE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
                    judged[0] += 1
                    if v:
                        fixed[0] += 1
                done[0] += len(b)
                print("  %d/%d (修 %d/评 %d)  %s" % (done[0], total, fixed[0], judged[0], b[0][0]), flush=True)
            time.sleep(0.3)

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    print("完成 %d（评 %d，修 %d），耗時 %.0fs" % (done[0], judged[0], fixed[0], time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
