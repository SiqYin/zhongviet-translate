#!/usr/bin/env python3
"""难词例句聚焦补跑：一次只处理一个词（单题提示），适配离合词/冷僻字。

结果写 data/ex_zh_cache.jsonl（断点续跑）。用法：
    python tools/ai_examples_focus.py --workers 6
"""
import argparse
import json
import pathlib
import queue
import re
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai_examples as ae

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ae.ZH_CACHE


def focused_prompt(w):
    return (f"请用词语「{w}」造一个中文例句。\n"
            f"硬性要求：例句中必须连续包含「{w}」原样，不得拆开、变形、增字。\n"
            f"若「{w}」是离合词（如“请假”），不要写成“请了一天假”，要写连写的“他请假了”这类形式。\n"
            f"例句 8~20 字，自然通顺，普通话。\n"
            f"只输出 JSON：{{\"{w}\": \"例句\"}}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    words = ae.load_words()
    zh = ae.load_jsonl(CACHE, "zh")
    todo = [w for w in words if w not in zh]
    if args.limit:
        todo = todo[:args.limit]
    print("聚焦补跑 %d 條" % len(todo), flush=True)
    if not todo:
        return

    q = queue.Queue()
    for w in todo:
        q.put(w)

    lock = threading.Lock()
    done = [0]
    ok = [0]

    def worker():
        while True:
            try:
                w = q.get_nowait()
            except queue.Empty:
                return
            got = {}
            for attempt in range(3):
                try:
                    txt = ae.post(focused_prompt(w), 600, model="Index-Translate-35B-A3B")
                    got = ae.parse_json(txt)
                    if not str(got.get(w, "")).strip():
                        raise ValueError("empty")
                    break
                except Exception:
                    got = {}
                    time.sleep(2 * (attempt + 1))
            v = ae.valid_zh(w, got.get(w, ""))
            with lock:
                if v:
                    zh[w] = v
                    with CACHE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
                    ok[0] += 1
                done[0] += 1
                if done[0] % 25 == 0:
                    print("  %d/%d (ok %d)  %s" % (done[0], len(todo), ok[0], w), flush=True)

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    print("完成 %d（有效 %d），耗時 %.0fs" % (done[0], ok[0], time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
