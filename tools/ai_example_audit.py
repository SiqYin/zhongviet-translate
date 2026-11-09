#!/usr/bin/env python3
"""審查並重寫詞庫例句。

兩階段：
1. 判定：逐條判斷例句是否通順、是否貼合詞頭義項，有問題的記入 data/ex_judge.jsonl；
2. 重寫：對有問題的例句，讓模型重寫一句自然的中文並給出越南語翻譯，
   記入 data/ex_fix_cache.jsonl。

可中斷續跑。重寫結果由 tools/apply_examples.py 寫回 app/zhvi.js。

    python tools/ai_example_audit.py --limit 200   # 試跑
    python tools/ai_example_audit.py                # 全量
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "zhvi.js"
JUDGE = ROOT / "data" / "ex_judge.jsonl"
FIX = ROOT / "data" / "ex_fix_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

BAD_ARCHAIC = ("若然", "信然", "倘然", "恁般", "恁么", "这般", "那般", "之乎者也")


def load_zv():
    src = SRC.read_text(encoding="utf-8")
    m = re.search(r"window\.ZV=(\[.*?\]);?\s*$", src, re.S)
    return json.loads(m.group(1))


def post(prompt, timeout=150):
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


def parse_json(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        return {}
    try:
        d = json.loads(text[i:j + 1])
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_jsonl(p, key="i"):
    d = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if key in o:
                d[o[key]] = o
    return d


def append_jsonl(p, rows, lock):
    with lock:
        with p.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def judge_prompt(batch):
    lines = []
    for n, (idx, hw, py, sense, zh) in enumerate(batch, 1):
        lines.append("%d|%s|%s|%s|%s" % (n, hw, py, (sense or "")[:20], zh))
    return (
        "下面是词典例句，格式为「序号|词头|拼音|义项|例句」。\n"
        "请找出其中明确有问题的例句：句子不成句、语义不通、明显病句、与词头义项完全不符、用文言或生造词。\n"
        "注意：仅仅不够生动、用词普通、句子很短，都不算问题，不要列出来。\n"
        "只输出 JSON：{\"bad\":[序号,...]}，没有问题的输出 {\"bad\":[]}。\n"
        + "\n".join(lines)
    )


def rewrite_prompt(batch):
    lines = []
    for n, (idx, hw, py, sense, zh) in enumerate(batch, 1):
        lines.append("%d|%s|%s|%s" % (n, hw, py, (sense or "")[:20]))
    return (
        "请用【简体中文】为下面每个词头各造一句自然、口语化的现代汉语句子（10-25 字），再给出对应的越南语翻译。\n"
        "第一个元素必须是简体中文句子（必须包含该词头），绝对不要用越南语写第一个元素；第二个元素才是越南语翻译。\n"
        "只用现代汉语常用词，禁止文言、生僻字、方言；句子要贴合给出的义项。\n"
        "示例：{\"1\":[\"他每天早上都喝一杯热茶。\",\"Anh ấy uống một ly trà nóng mỗi sáng.\"]}\n"
        "输入格式为「序号|词头|拼音|义项」。\n"
        "只输出 JSON：{\"1\":[\"汉语句子\",\"越南语翻译\"], ...}，不要解释。\n"
        + "\n".join(lines)
    )


def judge_worker(q, lock, out, stat):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        got = {}
        for a in range(3):
            try:
                got = parse_json(post(judge_prompt(batch)))
                if isinstance(got.get("bad"), list):
                    break
            except Exception:
                pass
            time.sleep(1.2 * (a + 1))
        rows = []
        if isinstance(got.get("bad"), list):
            bad = set()
            for x in got["bad"]:
                try:
                    bad.add(int(x))
                except Exception:
                    pass
            for n, item in enumerate(batch, 1):
                rows.append({"i": item[0], "bad": 1 if n in bad else 0})
            with lock:
                out.extend([item[0] for n, item in enumerate(batch, 1) if n in bad])
        else:
            with lock:
                stat["judge_fail"] += len(batch)
        append_jsonl(JUDGE, rows, lock)
        with lock:
            stat["judged"] += len(batch)
            if stat["judged"] % 2000 < len(batch):
                print("  判定 %d/%d  坏例句 %d" % (stat["judged"], stat["total"], len(out)), flush=True)


def fix_worker(q, lock, stat):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        got = {}
        for a in range(3):
            try:
                got = parse_json(post(rewrite_prompt(batch)))
                if got:
                    break
            except Exception:
                pass
            time.sleep(1.2 * (a + 1))
        rows = []
        for n, item in enumerate(batch, 1):
            idx, hw = item[0], item[1]
            v = got.get(str(n))
            if not (isinstance(v, list) and len(v) >= 2):
                continue
            zh, vi = str(v[0]).strip(), str(v[1]).strip()
            if hw not in zh or not (6 <= len(zh) <= 45) or not vi:
                continue
            if not re.search(r"[\u4e00-\u9fff]", zh):
                continue
            if not re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", vi):
                continue
            if False:
                continue
            if any(b in zh and b != hw for b in BAD_ARCHAIC):
                continue
            rows.append({"i": idx, "zh": zh, "vi": vi})
        if rows:
            append_jsonl(FIX, rows, lock)
        with lock:
            stat["fixed"] += len(rows)
            stat["tried"] += len(batch)
            if stat["tried"] % 500 < len(batch):
                print("  重写 %d/%d  成功 %d" % (stat["tried"], stat["fix_total"], stat["fixed"]), flush=True)


def run(fn, items, workers, batch_size, *args):
    q = queue.Queue()
    for i in range(0, len(items), batch_size):
        q.put(items[i:i + batch_size])
    ts = [threading.Thread(target=fn, args=(q, *args), daemon=True) for _ in range(workers)]
    [t.start() for t in ts]
    [t.join() for t in ts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--judge-batch", type=int, default=40)
    ap.add_argument("--fix-batch", type=int, default=12)
    args = ap.parse_args()

    ZV = load_zv()
    items = []
    for i, e in enumerate(ZV):
        ex = e[6]
        if isinstance(ex, list) and len(ex) == 2 and isinstance(ex[0], str) and ex[0]:
            items.append((i, e[1], e[2], (e[3] or "").split("；")[0], ex[0]))
    if args.limit:
        items = items[:args.limit]

    judged = load_jsonl(JUDGE)
    todo = [x for x in items if x[0] not in judged]
    print("例句 %d 条，已判定 %d，待判定 %d" % (len(items), len(judged), len(todo)), flush=True)

    lock = threading.Lock()
    stat = {"judged": 0, "total": len(todo), "judge_fail": 0, "fixed": 0, "tried": 0, "fix_total": 0}
    bad = []
    if todo:
        run(judge_worker, todo, args.workers, args.judge_batch, lock, bad, stat)
        print("判定完成：坏例句 %d，失败批 %d" % (len(bad), stat["judge_fail"]), flush=True)

    # 已判定为坏的（含之前轮次）
    bad_all = [x for x in items if judged.get(x[0], {}).get("bad") == 1]
    bad_all += [x for x in items if x[0] in set(bad) and x[0] not in {y[0] for y in bad_all}]
    fixed = load_jsonl(FIX)
    todo_fix = [x for x in bad_all if x[0] not in fixed]
    stat["fix_total"] = len(todo_fix)
    print("待重写 %d 条" % len(todo_fix), flush=True)
    if todo_fix:
        run(fix_worker, todo_fix, args.workers, args.fix_batch, lock, stat)
        print("重写完成：成功 %d / %d" % (stat["fixed"], stat["tried"]), flush=True)


if __name__ == "__main__":
    main()
