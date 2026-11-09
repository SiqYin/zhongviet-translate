#!/usr/bin/env python3
"""单音节越南语词的定向补跑：只处理 vi_gloss_cache 里还没覆盖的单音节词。

多音节词缺释义时退回旧词头问题不大（词头本身多半是对的），
单音节缺释义就会退回「咁/偌」这类生僻字，所以单独补一轮。

    python tools/ai_vi_single.py
"""
import json
import pathlib
import queue
import re
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai_vi_gloss as G

ROOT = pathlib.Path(__file__).resolve().parent.parent


def build_prompt(batch, refs):
    obj = {}
    for w in batch:
        rs = sorted(refs.get(w, ()), key=lambda z: (G.MODERN_RANK.get(z, 99999), len(z), z))[:5]
        obj[w] = rs
    return (
        "你是资深中越词典编辑。下面是越南语的单音节词。请为每个音节给出最贴切的现代汉语对应。\n"
        "参考栏是旧词典给的对应词，已滤掉生僻项，但可能不准或不全。\n"
        "规则：\n"
        "1. 汉越词给对应的汉语语素（可以是一个汉字，如 kinh→经、y→医）；纯越南语词给常用词。\n"
        "2. 只用一个汉字时，必须是现代汉语里能独立成词的常用字，不要用文言虚词或生僻字。\n"
        "3. 每个词给 1-3 个对应，按常用程度排序。\n"
        "4. 实在没有把握就给空数组 []，不要硬凑同音字。\n"
        "5. 只输出 JSON 对象，key 原样保留，value 是字符串数组。\n"
        "输入：" + json.dumps(obj, ensure_ascii=False)
    )


def run(todo, refs, workers, batch_size):
    q = queue.Queue()
    for i in range(0, len(todo), batch_size):
        q.put(todo[i:i + batch_size])
    lock = threading.Lock()
    left = []
    done = [0]

    def worker():
        while True:
            try:
                batch = q.get_nowait()
            except queue.Empty:
                return
            prompt = build_prompt(batch, refs)
            got = {}
            for a in range(3):
                try:
                    got = G.parse_json(G.post(prompt))
                    if got:
                        break
                except Exception:
                    pass
                time.sleep(1.2 * (a + 1))
            low = {k.lower().strip(): v for k, v in got.items() if isinstance(k, str)}
            lines, miss = [], []
            for w in batch:
                items = G.clean_list(low.get(w.lower().strip()), 1)
                if items:
                    lines.append(json.dumps({"w": w, "v": items}, ensure_ascii=False))
                else:
                    miss.append(w)
            with lock:
                if lines:
                    with G.CACHE.open("a", encoding="utf-8") as f:
                        f.write("\n".join(lines) + "\n")
                left.extend(miss)
                done[0] += len(batch)
                if done[0] % 200 < len(batch):
                    print("  %d/%d  %s" % (done[0], len(todo), batch[0]), flush=True)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return left


def main():
    phrases, refs = G.load_phrases()
    singles = sorted(w for w in phrases if len(w.split()) == 1)
    cache = G.load_cache()
    todo = [w for w in singles if w not in cache]
    print("单音节 %d 条，未覆盖 %d 条" % (len(singles), len(todo)), flush=True)
    if not todo:
        return
    t0 = time.time()
    left = run(todo, refs, 8, 12)
    print("第一轮完成，耗时 %.0fs，剩余 %d" % (time.time() - t0, len(left)), flush=True)
    if left:
        left = run(left, refs, 6, 4)
        print("补跑后剩余 %d" % len(left), flush=True)
    print("完成，缓存共 %d 条" % len(G.load_cache()), flush=True)


if __name__ == "__main__":
    main()
