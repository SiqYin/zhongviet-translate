#!/usr/bin/env python3
"""为词库里的越南语词生成现代汉语释义（直接翻译，不受旧候选限制）。

输出 data/vi_gloss_cache.jsonl，每行 {"w": 越南语词, "v": [中文释义...]}。
可中断续跑；失败批不落缓存。build_vi2zh.py 会把它合并进 app/vi2zh.js。

    python tools/ai_vi_gloss.py --limit 500   # 试跑
    python tools/ai_vi_gloss.py                # 全量（失败/空值会自动补跑两轮）
"""
import argparse
import csv
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
CACHE = ROOT / "data" / "vi_gloss_cache.jsonl"
MODERN = ROOT / "data" / "modern_chinese_words.tsv"

API = "https://index-translate.bilibili.com/v1/chat/completions"
MODEL = "Index-Translate-35B-A3B"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

MAX_SYL = 4
MAX_GLOSS = 4
MAX_LEN = 12

# 现代汉语常用词表：词语 -> 频序号（越小越常用）
MODERN_RANK = {}
COMMON_CHARS = set()
for _row in csv.DictReader(MODERN.open(encoding="utf-8"), delimiter="\t"):
    _w = (_row.get("词语") or "").strip()
    if not _w:
        continue
    try:
        _rank = int(_row.get("频序号") or 99999)
    except Exception:
        _rank = 99999
    if _w not in MODERN_RANK or _rank < MODERN_RANK[_w]:
        MODERN_RANK[_w] = _rank
    for _ch in _w:
        COMMON_CHARS.add(_ch)

# 文言虚词/古旧单字：即使出现在常用词表里，也不单独拿来当释义
BAD_SINGLE = set("乃然偌咁焉矣哉乎兮者之其此彼何莫弗毋勿欤耶尔汝吾予余曰云盖夫且若虽则即而所恁")

# 明确的文言/古旧词，禁止整词输出
BAD_WORDS = set("""
若然 信然 倘然 恁般 恁么 这般 那般 如此这般 之乎者也 呜呼哀哉 矣哉 焉哉
""".split())
CJK = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$")


def norm(s):
    s = re.sub(r"[（(][^）)]*[）)]", " ", (s or "").lower())
    s = re.sub(r"[.,;:!?\u201d\u2019\]\[]+$", "", s).strip()
    return re.sub(r"\s+", " ", s)


def load_phrases():
    src = SRC.read_text(encoding="utf-8")
    m = re.search(r"window\.ZV=(\[.*?\]);?\s*$", src, re.S)
    ZV = json.loads(m.group(1))
    phrases = set()
    refs = {}
    for e in ZV:
        zh = e[1]
        for raw in (e[3] or "").split("；"):
            s = norm(raw)
            if not s:
                continue
            n = len(s.split())
            if 1 <= n <= MAX_SYL:
                phrases.add(s)
                # 只把现代汉语常用词作为参考，挡掉咁/偌/乃这类旧候选
                if zh in MODERN_RANK and valid_gloss(zh):
                    refs.setdefault(s, set()).add(zh)
    return phrases, refs


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
            if isinstance(d.get("v"), list) and d.get("w") and d["v"]:
                cache[d["w"]] = d["v"]
    return cache


def clean_gloss(s):
    if not isinstance(s, str):
        return ""
    s = s.strip().strip('"\'“”‘’')
    s = re.sub(r"[（(][^）)]*[）)]", "", s)   # 去掉“（品牌）”“（人名）”这类注
    s = re.sub(r"[。；，、,.!?！？;:：]+$", "", s).strip()
    s = re.sub(r"\s+", "", s)
    return s


def valid_gloss(s):
    if not s or len(s) > MAX_LEN:
        return False
    if not CJK.match(s):
        return False
    if any(ch not in COMMON_CHARS for ch in s):
        return False
    if s in BAD_WORDS:
        return False
    if len(s) == 1:
        # 单字释义只收现代汉语能独立成词的常用字
        return s in MODERN_RANK and s not in BAD_SINGLE
    if len(s) == 2:
        # 双字词必须在现代常用词表里，挡掉若然/信然/倘然/恁般
        return s in MODERN_RANK
    # 三字以上：允许“滑盖手机”“拨号网络”这类描述性短语
    return True


def clean_list(v, min_len=1):
    out, seen = [], set()
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return out
    for x in v:
        s = clean_gloss(x)
        if len(s) < min_len:
            continue
        if valid_gloss(s) and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= MAX_GLOSS:
            break
    return out


def build_prompt(batch, refs):
    obj = {}
    for w in batch:
        rs = sorted(refs.get(w, ()), key=lambda z: (MODERN_RANK.get(z, 99999), len(z), z))[:6]
        obj[w] = rs
    return (
        "你是资深中越词典编辑。请为下面每个越南语词写出自然、通用的现代汉语（普通话）释义。\n"
        "每项后面的参考，是旧词典里对应的中文词；已筛掉生僻项，但仍可能不全或有错，仅供参考。\n"
        "规则：\n"
        "1. 只能使用现代汉语常用词，禁止生僻字、古汉语、文言文、粤语、方言、网络黑话。\n"
        "2. 每个词给 1-4 个最贴切的中文对应词，按常用程度从高到低排序；有多个常用义项就分别列出，参考不全时要补齐。\n"
        "3. 虚词、代词、连词、量词要给出语法义（例如 là→是，của→的，vậy→这样/那么，cho→给/让）。\n"
        "4. 只给词本身的独立义项，不要列比喻义、引申义或由它联想出来的形容词。\n"
        "5. 不要用同音字硬凑；单音节词按实际词义翻译，不要把一个音节硬塞成一个汉字。\n"
        "6. 两个音节以上的词，只给完整的词义，不要输出单个汉字。\n"
        "7. 汉越词按汉越义翻译；纯越南语词按越南语词义翻译；外来专名给通行中文译名。\n"
        "8. 只输出 JSON 对象，key 必须原样保留，value 是字符串数组。不要任何解释。\n"
        "示例：{\"vậy\":[\"这样\",\"那么\",\"如此\"],\"nước\":[\"水\",\"国家\"],"
        "\"gù\":[\"驼背\",\"咕噜\"],\"là\":[\"是\",\"属于\"]}\n"
        "输入：" + json.dumps(obj, ensure_ascii=False)
    )


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


def post(prompt, timeout=180):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
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


def run_batches(todo, refs, workers, batch_size, done, total):
    """跑一轮，返回没有拿到有效释义的词。"""
    if not todo:
        return []
    q = queue.Queue()
    for i in range(0, len(todo), batch_size):
        q.put(todo[i:i + batch_size])
    lock = threading.Lock()
    fail = []

    def worker():
        while True:
            try:
                batch = q.get_nowait()
            except queue.Empty:
                return
            prompt = build_prompt(batch, refs)
            got = {}
            for attempt in range(3):
                try:
                    got = parse_json(post(prompt))
                    if got:
                        break
                except Exception:
                    pass
                time.sleep(1.2 * (attempt + 1))
            low = {k.lower().strip(): v for k, v in got.items() if isinstance(k, str)}
            lines, missing = [], []
            for w in batch:
                min_len = 2 if len(w.split()) > 1 else 1
                items = clean_list(low.get(w.lower().strip()), min_len)
                if items:
                    lines.append(json.dumps({"w": w, "v": items}, ensure_ascii=False))
                else:
                    missing.append(w)
            with lock:
                if lines:
                    with CACHE.open("a", encoding="utf-8") as f:
                        f.write("\n".join(lines) + "\n")
                fail.extend(missing)
                done[0] += len(batch)
                if done[0] % 500 < len(batch):
                    print("  %d/%d  %s" % (done[0], total, batch[0]), flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--rounds", type=int, default=2)
    args = ap.parse_args()

    phrases, refs = load_phrases()
    # 单音节最常用，优先；同音节数按词长/字母序稳定
    ordered = sorted(phrases, key=lambda s: (len(s.split()), len(s), s))
    cache = load_cache()
    todo = [w for w in ordered if w not in cache]
    if args.limit:
        todo = todo[:args.limit]
    total = len(todo)
    print("待生成 %d 条（已缓存 %d / 词条池 %d）" % (total, len(cache), len(phrases)), flush=True)
    if not total:
        return

    t0 = time.time()
    done = [0]
    left = run_batches(todo, refs, args.workers, args.batch, done, total)
    print("第一轮完成 %d 条，耗时 %.0fs，缺 %d 条" % (total, time.time() - t0, len(left)), flush=True)

    # 缺的用更小批次补跑，模型偶尔漏 key / 给空数组
    for r in range(args.rounds):
        if not left:
            break
        time.sleep(2)
        print("补跑第 %d 轮：%d 条" % (r + 1, len(left)), flush=True)
        left = run_batches(left, refs, max(2, args.workers // 2), 8, [0], len(left))
        print("  剩余 %d 条" % len(left), flush=True)

    print("完成，缓存共 %d 条，未覆盖 %d 条" % (len(load_cache()), len(left)), flush=True)
    if left:
        print("未覆盖示例:", [w for w in left[:10]], flush=True)


if __name__ == "__main__":
    main()
