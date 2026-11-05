#!/usr/bin/env python3
"""用 Index-Translate 校正詞條：中文詞 -> 最常用越南語對應詞。

結果逐條寫入 data/ai_cache.jsonl，可中斷續跑。
用法：
    python tools/ai_correct.py --tier core --limit 120
    python tools/ai_correct.py --tier all
"""
import argparse
import json
import os
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
CACHE = ROOT / "data" / "ai_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

SWADESH = ["我", "你", "他", "这", "那", "谁", "什么", "不", "多", "少", "一", "二", "三",
           "四", "五", "大", "长", "小", "短", "女人", "男人", "人", "小孩", "妻子", "丈夫",
           "母亲", "父亲", "动物", "鱼", "鸟", "狗", "蛇", "虫", "树", "森林", "水果", "种子",
           "叶子", "根", "花", "草", "绳子", "皮肤", "肉", "血", "骨头", "蛋", "角", "尾巴",
           "羽毛", "头发", "头", "耳朵", "眼睛", "鼻子", "嘴", "牙齿", "舌头", "脚", "腿",
           "手", "翅膀", "肚子", "脖子", "背", "心", "肝", "喝", "吃", "咬", "吐", "吹",
           "笑", "看", "听", "知道", "想", "怕", "睡", "死", "杀", "打", "切", "抓", "飞",
           "走", "来", "躺", "坐", "站", "转", "给", "拿", "洗", "拉", "推", "扔", "说",
           "唱", "玩", "太阳", "月亮", "星星", "水", "雨", "河", "湖", "海", "盐", "石头",
           "沙子", "土", "云", "风", "雪", "冰", "火", "路", "山", "红", "绿", "黄", "白",
           "黑", "夜", "白天", "年", "冷", "新", "旧", "好", "坏", "圆", "湿", "干", "近",
           "远", "右", "左", "里", "名字"]

_locks = threading.Lock()


def load_words():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    have = {}
    for e in src:
        have.setdefault(e["s"], e)
        if e["t"] != e["s"]:
            have.setdefault(e["t"], e)

    core = []
    hsk = ROOT / "data" / "hsk_all.tsv"
    if hsk.exists():
        for line in hsk.read_text(encoding="utf-8-sig").splitlines():
            p = line.split("\t")
            if len(p) >= 2:
                core.append(p[0].strip())
                core.append(p[1].strip())
    core += SWADESH

    singles = [e["s"] for e in src if len(e["s"]) == 1 and CJK.match(e["s"])]

    core = [w for w in core if w in have]
    singles = [w for w in singles if w in have]
    return core, singles


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
            if d.get("v"):
                cache[d["w"]] = d["v"]
    return cache


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


def build_prompt(words):
    payload = {w: "" for w in words}
    return (
        "请将以下中文文本翻译成越南语，并且严格遵循所有约束要求。\n\n"
        "【源文】\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\n【约束要求】\n"
        "1. 【硬性要求】每个 value 只填最常用的 1 个越南语对应词，不要解释，不要标点\n"
        "2. 【硬性要求】保留 JSON 结构，key 保持不变\n"
        "3. 【硬性要求】不要把中文词原样抄回 value\n\n"
        "请以相同的 JSON 格式输出翻译结果，key 保持不变，value 为对应译文。"
        "只输出 JSON，不要有任何额外说明。"
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
    if not v or CJK.search(v) or len(v) > 40 or len(v.split()) > 5:
        return ""
    if v.startswith("(") or "/" in v:
        return ""
    return v


def worker(q, cache, lock, done, total, stop):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        if stop.is_set():
            return
        prompt = build_prompt(batch)
        for attempt in range(3):
            try:
                txt = post(prompt)
                got = parse_json(txt)
                break
            except Exception as e:
                got = {}
                if attempt == 2:
                    with lock:
                        print("  ! batch failed:", batch[0], e, flush=True)
                time.sleep(1.5 * (attempt + 1))
        with lock:
            for w in batch:
                v = valid(w, got.get(w, ""))
                if v:
                    cache[w] = v
                    with CACHE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
            done[0] += len(batch)
            print("  %d/%d  %s" % (done[0], total, batch[0]), flush=True)
        time.sleep(0.25)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--tier", default="core", choices=["core", "single", "all"])
    args = ap.parse_args()

    core, singles = load_words()
    if args.tier == "single":
        pool = singles
    elif args.tier == "core":
        pool = core
    else:
        pool = core + singles
    seen, words = set(), []
    for w in pool:
        if w not in seen:
            seen.add(w)
            words.append(w)

    cache = load_cache()
    todo = [w for w in words if w not in cache]
    if args.limit:
        todo = todo[:args.limit]

    total = len(todo)
    print("待校正 %d 條（已快取 %d）" % (total, len(cache)), flush=True)
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
    print("完成 %d 條，耗時 %.0fs，快取共 %d" % (done[0], time.time() - t0, len(cache)), flush=True)


if __name__ == "__main__":
    main()
