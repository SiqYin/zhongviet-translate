#!/usr/bin/env python3
"""例句生成（两段式）：先造中文例句，再批量翻成越南语。

阶段1 结果 data/ex_zh_cache.jsonl   {w: 中文例句}
阶段2 结果 data/ex_vi_cache.jsonl   {w: [中文例句, 越南语译文]}
用法：
    python tools/ai_examples.py --phase zh --limit 100
    python tools/ai_examples.py --phase vi --limit 100
    python tools/ai_examples.py --phase all
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
ZH_CACHE = ROOT / "data" / "ex_zh_cache.jsonl"
VI_CACHE = ROOT / "data" / "ex_vi_cache.jsonl"
FIX_CACHE = ROOT / "data" / "ex_fix_cache.jsonl"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL_ZH = "Index-Translate-9B"
MODEL_VI = "Index-Translate-2B"     # 翻譯本職，快且穩；key 用序號避免中文 key 被改寫
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CJK = re.compile(r"[㐀-䶿一-鿿]")
LATIN_VI = re.compile(r"[A-Za-zÀ-ỹ]")


def load_words():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    seen, allw = set(), []
    for e in src:
        s = e.get("s") or ""
        if s and s not in seen and CJK.search(s):
            seen.add(s)
            allw.append(s)
    # 常用優先：HSK → 單字 → 全部
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


def load_jsonl(path, mode):
    cache = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            w, v = d.get("w"), d.get("v")
            if not w:
                continue
            if mode == "zh" and isinstance(v, str) and v:
                cache[w] = v
            elif mode == "vi" and isinstance(v, list) and len(v) >= 2:
                cache[w] = v
    return cache


def post(prompt, maxtok, timeout=200, model=None):
    body = json.dumps({
        "model": model or MODEL_ZH,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": maxtok,
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
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        return {}
    s = text[i:j + 1]
    s = re.sub(r",\s*([}\]])", r"\1", s)      # 尾逗号容錯（2B/9B 常見）
    try:
        return json.loads(s)
    except Exception:
        pass
    # 兜底：逐鍵正則搶救（容忍壞引號/截斷）
    out = {}
    for m in re.finditer(r'"([^"]{1,24})"\s*:\s*"((?:[^"\\]|\\.)*)"', s):
        out[m.group(1)] = m.group(2)
    return out


def zh_prompt(words):
    payload = {w: "" for w in words}
    return (
        "请给下面每个中文词写一个中文例句，填进 JSON 的 value。\n"
        "要求：例句 8~20 字、必须是语法正确、自然通顺的普通话句子；\n"
        "例句中必须完整原样出现该词条（如「请假」写成“他请假了”，不能写成“请了一天假”；不能拆开、变形或增字）。\n"
        "禁止病句（如“请对不起”）；禁止出现任何字母或越南语。\n"
        "示例：输入 {\"鸡\":\"\",\"火车\":\"\"} → 输出 {\"鸡\":\"妈妈炖了一锅鸡汤。\",\"火车\":\"火车晚点了十分钟。\"}\n"
        "只输出 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def vi_prompt(pairs):
    """pairs: [(w, zh_sentence), ...] — key 用序號，避免模型改寫中文 key。"""
    payload = {"k%d" % i: s for i, (_, s) in enumerate(pairs)}
    return (
        "把下面 JSON 里每个中文句子翻译成越南语，填进对应的 value。key（k0/k1/...）原样保留。\n"
        "示例：输入 {\"k0\":\"妈妈炖了一锅鸡汤。\"} → 输出 {\"k0\":\"Mẹ nấu một nồi canh gà.\"}\n"
        "value 必须是越南语译文，地道自然，禁止逐字直译。只输出 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def valid_zh(word, val):
    v = (val or "").strip() if isinstance(val, str) else ""
    if not v or not CJK.search(v):
        return ""
    if LATIN_VI.search(v):
        return ""
    if word not in v:
        # 离合词拆开（请了一天假 / 打了个喷嚏）也算用法示範：字按序全出現
        it = iter(v)
        if not all(ch in it for ch in word):
            return ""
    if len(v) < 6 or len(v) > 60:
        return ""
    # 實義字符太少 = 偷懶短句，重來
    if len(CJK.findall(v)) < 5:
        return ""
    return v


def valid_vi(val):
    v = (val or "").strip() if isinstance(val, str) else ""
    if not v or CJK.search(v):
        return ""
    if len(v) > 120 or len(v.split()) > 25:
        return ""
    return v


def run_phase(phase, words_todo, cache, cachepath, workers, batch):
    q = queue.Queue()
    for i in range(0, len(words_todo), batch):
        q.put(words_todo[i:i + batch])

    lock = threading.Lock()
    done = [0]
    ok = [0]
    total = len(words_todo)

    def worker():
        while True:
            try:
                b = q.get_nowait()
            except queue.Empty:
                return
            got = {}
            for attempt in range(4):
                try:
                    if phase == "zh":
                        txt = post(zh_prompt(b), 4000, model=MODEL_ZH)
                        got = parse_json(txt)
                    else:
                        pairs = [(w, cache[w]) for w in b]
                        txt = post(vi_prompt(pairs), 5000, model=MODEL_VI)
                        raw = parse_json(txt)
                        # 35B 偶爾把 "k9" 寫成 "9"，兩種 key 都收
                        got = {b[i]: raw.get("k%d" % i, raw.get(str(i), ""))
                               for i in range(len(b))}
                    if not any(str(v).strip() for v in got.values()):
                        raise ValueError("empty")
                    break
                except Exception as e:
                    got = {}
                    if attempt == 3:
                        with lock:
                            print("  ! batch failed:", b[0], e, flush=True)
                    time.sleep(3 * (attempt + 1))
            with lock:
                n = 0
                for w in b:
                    if phase == "zh":
                        v = valid_zh(w, got.get(w, ""))
                    else:
                        vi = valid_vi(got.get(w, ""))
                        v = [cache[w], vi] if vi else ""
                    if v:
                        cache[w] = v if phase == "vi" else v
                        with cachepath.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"w": w, "v": v}, ensure_ascii=False) + "\n")
                        n += 1
                done[0] += len(b)
                ok[0] += n
                print("  %s %d/%d (ok %d)  %s" % (phase, done[0], total, ok[0], b[0]), flush=True)
            time.sleep(0.3)

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    print("[%s] 完成 %d 條（有效 %d），耗時 %.0fs" % (phase, done[0], ok[0], time.time() - t0), flush=True)


def main():
    global MODEL_ZH, MODEL_VI, VI_CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["zh", "vi", "all"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--model-zh", default=MODEL_ZH)
    ap.add_argument("--model-vi", default=MODEL_VI)
    ap.add_argument("--vi-cache", default=str(VI_CACHE))
    args = ap.parse_args()

    MODEL_ZH = args.model_zh
    MODEL_VI = args.model_vi
    VI_CACHE = pathlib.Path(args.vi_cache)
    words = load_words()

    if args.phase in ("zh", "all"):
        zhc = load_jsonl(ZH_CACHE, "zh")
        todo = [w for w in words if w not in zhc]
        if args.limit:
            todo = todo[:args.limit]
        print("[zh] 待造例句 %d（已快取 %d）" % (len(todo), len(zhc)), flush=True)
        if todo:
            run_phase("zh", todo, zhc, ZH_CACHE, args.workers, args.batch)

    if args.phase in ("vi", "all"):
        zhc = load_jsonl(ZH_CACHE, "zh")
        # 病句筛修后的句子优先（vi 译文必须对应最终中文例句）
        if FIX_CACHE.exists():
            for line in FIX_CACHE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("w") and isinstance(d.get("v"), str) and d["v"]:
                    zhc[d["w"]] = d["v"]
        vic = load_jsonl(VI_CACHE, "vi")
        todo = [w for w in words if w in zhc and w not in vic]
        if args.limit:
            todo = todo[:args.limit]
        print("[vi] 待翻译例句 %d（已快取 %d）" % (len(todo), len(vic)), flush=True)
        if todo:
            run_phase("vi", todo, zhc, VI_CACHE, args.workers, args.batch)


if __name__ == "__main__":
    main()
