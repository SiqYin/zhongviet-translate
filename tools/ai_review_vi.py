#!/usr/bin/env python3
"""译文筛修：检查双语例句的越南语译文，错译/生硬直译给修正，自然的留空。

输出 data/ex_vi_fix_cache.jsonl  {w: 修正后的越南语译文}。
用法：
    python tools/ai_review_vi.py --workers 8
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
VI_CACHE = ROOT / "data" / "ex_vi_cache.jsonl"
CACHE = ROOT / "data" / "ex_vi_fix_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[㐀-䶿一-鿿]")


def load_pairs():
    out = {}
    if VI_CACHE.exists():
        for line in VI_CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            w, v = d.get("w"), d.get("v")
            if w and isinstance(v, list) and len(v) >= 2:
                out[w] = [str(v[0]).strip(), str(v[1]).strip()]
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
        "max_tokens": 5000,
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


def build_prompt(items):
    """items: [(idx, zh, vi), ...]"""
    payload = {"k%d" % i: [zh, vi] for i, zh, vi in items}
    return (
        "下面 JSON 的每个 value 是 [中文例句, 越南语译文]。请检查越南语译文：\n"
        "若译文准确、地道，填空字符串 \"\"；\n"
        "若译文有错译、生硬直译、术语不当或不通顺，填修正后的越南语译文（地道自然的完整句子）。\n"
        "示例：输入 {\"k0\":[\"宇宙线是高能粒子流。\",\"Tia vũ trụ là một dòng hạt năng lượng cao.\"]} → 输出 {\"k0\":\"\"}\n"
        "示例：输入 {\"k1\":[\"国际音标帮助学习发音。\",\"Phoneme quốc tế giúp học cách phát âm.\"]} → 输出 {\"k1\":\"Phiên âm quốc tế giúp học cách phát âm.\"}\n"
        "key（k0/k1/...）原样保留。只输出 JSON。\n\n"
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
        pass
    out = {}
    for m in re.finditer(r'"(k\d+)"\s*:\s*"((?:[^"\\]|\\.)*)"', s):
        out[m.group(1)] = m.group(2)
    return out


def valid(val, orig_vi):
    # 模型常回顯 [原译, 修正] 数组——取第二元素作修正结果
    if isinstance(val, list):
        val = val[1] if len(val) >= 2 else ""
    if not isinstance(val, str):
        return None
    v = val.strip()
    if not v:
        return ""
    if CJK.search(v):
        return None
    if v == orig_vi:
        return ""
    if len(v) > 140 or len(v.split()) > 30:
        return None
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=15)
    args = ap.parse_args()

    pairs = load_pairs()
    cache = load_cache()
    todo = [(w, zh, vi) for w, (zh, vi) in pairs.items() if w not in cache]
    if args.limit:
        todo = todo[:args.limit]
    total = len(todo)
    print("待評 %d（已評 %d）" % (total, len(cache)), flush=True)
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
                    txt = post(build_prompt([(i, zh, vi) for i, (w, zh, vi) in enumerate(b)]))
                    got = parse_json(txt)
                    if not any(k in got for k in ("k%d" % i for i in range(len(b)))):
                        raise ValueError("no keys")
                    break
                except Exception as e:
                    got = {}
                    if attempt == 3:
                        with lock:
                            print("  ! batch failed:", b[0][0], e, flush=True)
                    time.sleep(3 * (attempt + 1))
            with lock:
                for i, (w, zh, vi) in enumerate(b):
                    v = valid(got.get("k%d" % i, ""), vi)
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
