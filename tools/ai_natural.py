#!/usr/bin/env python3
"""判改「偏直译」的越南语对应：只对可疑词条判定，需改才给自然译法。

输入当前首义，模型判断是否逐字直译/不地道；需要改时给自然越南语，不需要则输出空串。
结果逐条写入 data/natural_cache.jsonl，可中断续跑。
用法：
    python tools/ai_natural.py --limit 100     # 试跑
    python tools/ai_natural.py --workers 3
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
SRC = ROOT / "data" / "zhvi_src.json"
FIX = ROOT / "data" / "ai_fix.json"
CACHE = ROOT / "data" / "natural_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[㐀-䶿一-鿿]")
DEFI = re.compile(r"nghĩa đen|có nghĩa là|được gọi là|có thể gọi là|nghĩa là", re.I)


def load_candidates():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    fix = json.loads(FIX.read_text(encoding="utf-8")) if FIX.exists() else {}
    seen, out = set(), []
    for e in src:
        w = e.get("s") or ""
        if not w or w in seen or len(w) < 2 or not CJK.search(w):
            continue
        seen.add(w)
        cur = (fix.get(w) or (e["g"][0] if e.get("g") else "")).strip()
        n = len(cur.split())
        if not cur or DEFI.search(cur) or (n >= len(w) and n >= 3):
            out.append((w, cur))
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
        "max_tokens": 3000,
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
    """pairs: [(word, current_vi), ...]"""
    payload = {w: cur for w, cur in pairs}
    return (
        "下面 JSON 的每个 key 是中文词，value 是它当前的越南语对应。\n"
        "请判断 value 是否为逐字直译或不地道的越南语。若不地道，填入更自然、更常用的越南语对应词"
        "（词语或短语，最多 5 个词，禁止逐字直译，专有名词用通行译名）；若已经自然地道，填空字符串 \"\"。\n"
        "示例：输入 {\"铁饭碗\":\"bát cơm sắt\"} → 输出 {\"铁饭碗\":\"công việc ổn định\"}\n"
        "示例：输入 {\"图书馆\":\"thư viện\"} → 输出 {\"图书馆\":\"\"}\n"
        "key 原样保留。只输出 JSON。\n\n"
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
    if not isinstance(val, str):
        return ""
    v = val.strip().strip(".,;:!?\"'")
    if not v:
        return ""                      # 空 = 保留原值，合法
    if CJK.search(v) or len(v) > 40 or len(v.split()) > 5:
        return None                    # 不合格
    if v.lower() == word.lower():
        return None
    return v


def worker(q, cache, lock, done, total, stat):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        prompt = build_prompt(batch)
        got = {}
        for attempt in range(4):
            try:
                txt = post(prompt)
                got = parse_json(txt)
                if not any(k in got for k, _ in batch):
                    raise ValueError("no keys")
                break
            except Exception as e:
                got = {}
                if attempt == 3:
                    with lock:
                        print("  ! batch failed:", batch[0][0], e, flush=True)
                time.sleep(3 * (attempt + 1))
        with lock:
            for w, cur in batch:
                v = valid(w, got.get(w, ""))
                if v is None:
                    continue             # 不合格，留待续跑
                # 回抄原值 = 无需改动，记为空
                if v and v.lower().strip(" .,;:") == (cur or "").lower().strip(" .,;:"):
                    v = ""
                cache[w] = v
                with CACHE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
                stat[0] += 1 if v else 0
                stat[1] += 1
            done[0] += len(batch)
            print("  %d/%d (改 %d/评 %d)  %s" % (done[0], total, stat[0], stat[1], batch[0][0]), flush=True)
        time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=30)
    args = ap.parse_args()

    cands = load_candidates()
    cache = load_cache()
    todo = [(w, c) for w, c in cands if w not in cache]
    if args.limit:
        todo = todo[:args.limit]
    total = len(todo)
    print("可疑词条 %d，已评 %d，本次待评 %d" % (len(cands), len(cache), total), flush=True)
    if not total:
        return

    q = queue.Queue()
    for i in range(0, total, args.batch):
        q.put(todo[i:i + args.batch])

    lock = threading.Lock()
    done, stat = [0], [0, 0]
    threads = [threading.Thread(target=worker, args=(q, cache, lock, done, total, stat), daemon=True)
               for _ in range(args.workers)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("完成 %d 條（其中需改 %d），耗時 %.0fs" % (stat[1], stat[0], time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
