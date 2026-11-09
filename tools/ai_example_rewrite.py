#!/usr/bin/env python3
"""重寫有問題的例句：先造中文句，再翻越南語。

問題句由規則挑出（data/ex_flag_ids.json）：定義式（是一種/是指/讀作）、
過短、文言腔、標點異常。

兩階段：
1. 造中文句：輸入「序號|詞頭|拼音|中文義項」，輸出按位置對應的句子數組；
   不合格（沒出現詞頭、帶回輸入行、太短、又寫成定義式）自動再試一輪。
2. 翻越南語：把新造的中文句批量翻成越南語。

結果分別寫 data/ex_new_zh.jsonl、data/ex_new_vi.jsonl，
由 tools/apply_examples.py 合併寫回 app/zhvi.js。

    python tools/ai_example_rewrite.py --limit 200
    python tools/ai_example_rewrite.py
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
VI2ZH = ROOT / "app" / "vi2zh.js"
FLAG = ROOT / "data" / "ex_flag_ids.json"
OUT_ZH = ROOT / "data" / "ex_new_zh.jsonl"
OUT_VI = ROOT / "data" / "ex_new_vi.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
DEF = re.compile(r"(是一种|是指|指的是|是古代|的称呼|的意思|读作|这个字|该字|念作)")
VI_CHARS = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")


def load_zv():
    src = SRC.read_text(encoding="utf-8")
    m = re.search(r"window\.ZV=(\[.*?\]);?\s*$", src, re.S)
    return json.loads(m.group(1))


def load_vi2zh():
    s = VI2ZH.read_text(encoding="utf-8")
    return json.loads(s[s.find("=") + 1:s.rfind(";")])


def post(prompt, timeout=150):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
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


def gen_prompt(batch, strict=False):
    lines = ["%d|%s|%s|%s" % (n, hw, py, sense or "（不限）")
             for n, (idx, hw, py, sense) in enumerate(batch, 1)]
    head = ("为下面每个中文词头各造一句自然通顺的现代汉语句子（10-25字），句子里必须出现该词头，并贴合义项。\n"
            "只用现代汉语常用词，不要文言、生僻字、方言；不要写成「X是一种……」「X指……」这类解释句。\n"
            "输入格式为「序号|词头|拼音|义项」。\n"
            "只输出 JSON：{\"s\":[\"第1句\",\"第2句\",...]}，数组长度和输入条数相同，顺序一一对应，不要回抄输入。\n")
    if strict:
        head = ("上一轮造句不合格。这次每句必须原样出现对应的词头，且只输出句子本身，不要带序号、竖线或拼音。\n" + head)
    return head + "\n".join(lines)


def trans_prompt(batch):
    lines = ["%d|%s" % (n, zh) for n, (idx, zh) in enumerate(batch, 1)]
    return ("把下面每句中文翻成自然通顺的越南语，保持原意。\n"
            "只输出 JSON：{\"s\":[\"第1句越南语\",\"第2句越南语\",...]}，数组长度和输入条数相同，顺序一一对应。\n"
            "输入格式为「序号|中文句子」。\n" + "\n".join(lines))


def load_jsonl(p):
    d = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if "i" in o:
                d[o["i"]] = o
    return d


def append_jsonl(p, rows, lock):
    if not rows:
        return
    with lock:
        with p.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ok_sentence(hw, zh):
    if not zh or "|" in zh:
        return False
    if hw not in zh:
        return False
    if not (7 <= len(zh) <= 42):
        return False
    if DEF.search(zh):
        return False
    if not re.search(r"[\u4e00-\u9fff]", zh):
        return False
    return True


def gen_worker(q, lock, stat, strict=False):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        got = {}
        for a in range(3):
            try:
                got = parse_json(post(gen_prompt(batch, strict)))
                if isinstance(got.get("s"), list):
                    break
            except Exception:
                pass
            time.sleep(1.2 * (a + 1))
        arr = got.get("s") if isinstance(got.get("s"), list) else []
        rows, retry = [], []
        for n, item in enumerate(batch):
            zh = str(arr[n]).strip() if n < len(arr) else ""
            if ok_sentence(item[1], zh):
                rows.append({"i": item[0], "zh": zh})
            elif not strict:
                retry.append(item)
        append_jsonl(OUT_ZH, rows, lock)
        with lock:
            stat["gen_ok"] += len(rows)
            stat["gen_tried"] += len(batch)
            stat["retry"].extend(retry)
            if stat["gen_tried"] % 400 < len(batch):
                print("  造句 %d/%d 成功 %d" % (stat["gen_tried"], stat["gen_total"], stat["gen_ok"]), flush=True)


def trans_worker(q, lock, stat, strict=False):
    while True:
        try:
            batch = q.get_nowait()
        except queue.Empty:
            return
        got = {}
        for a in range(3):
            try:
                got = parse_json(post(trans_prompt(batch)))
                if isinstance(got.get("s"), list):
                    break
            except Exception:
                pass
            time.sleep(1.2 * (a + 1))
        arr = got.get("s") if isinstance(got.get("s"), list) else []
        rows = []
        for n, (idx, zh) in enumerate(batch):
            vi = str(arr[n]).strip() if n < len(arr) else ""
            if vi and "|" not in vi and VI_CHARS.search(vi):
                rows.append({"i": idx, "vi": vi})
        append_jsonl(OUT_VI, rows, lock)
        with lock:
            stat["trans_ok"] += len(rows)
            stat["trans_tried"] += len(batch)
            if stat["trans_tried"] % 400 < len(batch):
                print("  翻译 %d/%d 成功 %d" % (stat["trans_tried"], stat["trans_total"], stat["trans_ok"]), flush=True)


def run(fn, items, workers, batch_size, lock, stat, strict=False):
    q = queue.Queue()
    for i in range(0, len(items), batch_size):
        q.put(items[i:i + batch_size])
    ts = [threading.Thread(target=fn, args=(q, lock, stat), kwargs={"strict": strict}, daemon=True)
          for _ in range(workers)]
    [t.start() for t in ts]
    [t.join() for t in ts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    ZV = load_zv()
    VI = load_vi2zh()
    ids = json.loads(FLAG.read_text(encoding="utf-8")) if FLAG.exists() else []
    if args.limit:
        ids = ids[:args.limit]

    # 只重写能独立成词的单字和多字词；不能独立成词的单字（丽/乃/丞）硬造句只会更糟
    modern = set()
    mpath = ROOT / "data" / "modern_chinese_words.tsv"
    if mpath.exists():
        import csv as _csv
        for row in _csv.DictReader(mpath.open(encoding="utf-8"), delimiter="\t"):
            w = (row.get("词语") or "").strip()
            if w:
                modern.add(w)

    items, skipped = [], 0
    for i in ids:
        e = ZV[i]
        if len(e[1]) == 1 and e[1] not in modern:
            skipped += 1
            continue
        sense = (e[3] or "").split("；")[0]
        gloss = VI.get(sense) or []
        items.append((i, e[1], e[2], "/".join(gloss[:2])))
    print("不可独立成词的单字跳过 %d 条" % skipped, flush=True)

    done = load_jsonl(OUT_ZH)
    todo = [x for x in items if x[0] not in done]
    print("待造句 %d 条（已完成 %d）" % (len(todo), len(done)), flush=True)

    lock = threading.Lock()
    stat = {"gen_ok": 0, "gen_tried": 0, "gen_total": len(todo), "retry": [],
            "trans_ok": 0, "trans_tried": 0, "trans_total": 0}
    if todo:
        run(gen_worker, todo, args.workers, 12, lock, stat)
        print("造句完成 %d/%d，待加强 %d" % (stat["gen_ok"], len(todo), len(stat["retry"])), flush=True)
        if stat["retry"]:
            run(gen_worker, stat["retry"], args.workers, 8, lock, stat, strict=True)
            print("加强后累计造句 %d" % stat["gen_ok"], flush=True)

    done = load_jsonl(OUT_ZH)
    got_vi = load_jsonl(OUT_VI)
    todo_t = [(i, done[i]["zh"]) for i in done if i not in got_vi]
    stat["trans_total"] = len(todo_t)
    print("待翻译 %d 条" % len(todo_t), flush=True)
    if todo_t:
        run(trans_worker, todo_t, args.workers, 20, lock, stat)
        print("翻译完成 %d/%d" % (stat["trans_ok"], len(todo_t)), flush=True)
    print("总完成 中文 %d / 越南语 %d" % (len(load_jsonl(OUT_ZH)), len(load_jsonl(OUT_VI))), flush=True)


if __name__ == "__main__":
    main()
