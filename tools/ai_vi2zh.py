#!/usr/bin/env python3
"""越南語 -> 中文：對詞庫裡有多個候選中文詞的越南語詞做一輪 AI 精排。

從 app/zhvi.js 反演全部越南語義項（1-4 音節），把「候選中文詞 >= 2」的詞
送 Index-Translate 排序去雜（只准從候選裡選），結果寫入 data/ai_vi2zh_cache.jsonl，
可中斷續跑。build_vi2zh.py 會把快取併進 app/vi2zh.js。

用法：
    python tools/ai_vi2zh.py                # 全部多候選詞
    python tools/ai_vi2zh.py --limit 200    # 試跑
"""
import argparse
import json
import pathlib
import queue
import re
import sys
import threading
import time
import urllib.request

try:  # 控制台是 GBK 時避免打印越南語崩潰
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "zhvi.js"
CACHE = ROOT / "data" / "ai_vi2zh_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

MAX_SYL = 4


def norm(s):
    s = re.sub(r"[（(][^）)]*[）)]", " ", (s or "").lower())
    s = re.sub(r"[.,;:!?\u201d\u2019\]\[]+$", "", s).strip()
    return re.sub(r"\s+", " ", s)


def load_candidates():
    src = SRC.read_text(encoding="utf-8")
    m = re.search(r"window\.ZV=(\[.*?\]);?\s*$", src, re.S)
    ZV = json.loads(m.group(1))
    cand = {}
    for e in ZV:
        zh = e[1]
        for j, raw in enumerate((e[3] or "").split("；")):
            s = norm(raw)
            if not s:
                continue
            sy = s.split()
            if 1 <= len(sy) <= MAX_SYL:
                cand.setdefault(s, []).append((zh, e[2], j))
    # 同一中文詞只保留一個候選（優先義項位置靠前的）
    out = {}
    for phrase, lst in cand.items():
        seen = {}
        for zh, py, j in lst:
            if zh not in seen or j < seen[zh][2]:
                seen[zh] = (zh, py, j)
        out[phrase] = sorted(seen.values(), key=lambda c: c[2])
    return out


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
            if isinstance(d.get("v"), list):
                cache[d["w"]] = d["v"]
    return cache


def build_prompt(batch):
    payload = {p: [c[0] for c in cand_list[:10]] for p, cand_list in batch}
    return (
        "你在整理一本越南语→中文词典。下面 JSON 里每个 key 是一个越南语词，"
        "value 是词库中候选的中文对应词（可能混有生僻字或错误条目）。\n"
        "请为每个越南语词选出最贴切、最常用的中文翻译，按贴切程度从高到低排序，最多 4 个；"
        "只能从候选里选，去掉明显不对的；如果候选全都不对就输出空数组 []。\n"
        "示例：输入 {\"nước\":[\"歊\",\"水\",\"氵\",\"国家\"]} → 输出 {\"nước\":[\"水\",\"国家\"]}\n"
        "key 必须原样保留。只输出 JSON，不要任何解释。\n\n"
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


def post(prompt, timeout=150):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
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


def valid_items(phrase, cand_list, got):
    ok = set(c[0] for c in cand_list)
    out = []
    seen = set()
    if not isinstance(got, list):
        return out
    for v in got:
        if isinstance(v, str):
            v = v.strip()
            if v in ok and v not in seen:
                seen.add(v)
                out.append(v)
    return out[:4]


def worker(q, lock, done, total):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        prompt = build_prompt(batch)
        got = {}
        ok = False
        for attempt in range(4):
            try:
                got = parse_json(post(prompt))
                if not isinstance(got, dict):
                    got = {}
                if got:
                    ok = True
                    break
                ok = True        # 模型正常回應（哪怕全空）也算了成功
                break
            except Exception as e:
                if attempt == 3:
                    with lock:
                        print("  ! batch failed:", batch[0][0], repr(e)[:100], flush=True)
                time.sleep(2.0 * (attempt + 1))
        if not ok:
            continue             # 失敗批不寫緩存，下次續跑重試
        lines = []
        with lock:
            try:
                for phrase, cand_list in batch:
                    items = valid_items(phrase, cand_list, got.get(phrase))
                    lines.append(json.dumps({"w": phrase, "v": items}, ensure_ascii=False))
                with CACHE.open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except Exception as e:
                print("  ! write failed:", repr(e)[:160], flush=True)
            done[0] += len(batch)
            if done[0] % 200 < len(batch):
                print("  %d/%d  %s" % (done[0], total, batch[0][0]), flush=True)
        time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    cand = load_candidates()
    pool = [(p, c) for p, c in cand.items() if len(c) >= 2]
    # 單音節優先（用戶最常敲），其後按候選數降冪
    pool.sort(key=lambda pc: (len(pc[0].split()), -len(pc[1]), pc[0]))

    cache = load_cache()
    todo = [(p, c) for p, c in pool if p not in cache]
    if args.limit:
        todo = todo[:args.limit]

    total = len(todo)
    print("待精排 %d 條（已快取 %d / 候選池 %d）" % (total, len(cache), len(pool)), flush=True)
    if not total:
        return

    q = queue.Queue()
    for i in range(0, total, args.batch):
        q.put(todo[i:i + args.batch])

    lock = threading.Lock()
    done = [0]
    threads = [threading.Thread(target=worker, args=(q, lock, done, total), daemon=True)
               for _ in range(args.workers)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("完成 %d 條，耗時 %.0fs，快取共 %d" % (total, time.time() - t0, len(load_cache())), flush=True)


if __name__ == "__main__":
    main()
