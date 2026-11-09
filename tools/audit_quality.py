#!/usr/bin/env python3
import json, re, pathlib, collections, random, sys
ROOT = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/01_源码/hanviet-app')
src = (ROOT/'app/zhvi.js').read_text(encoding='utf-8')
ZV = json.loads(re.search(r'window\.ZV=(\[.*?\]);?\s*$', src, re.S).group(1))
vsrc = (ROOT/'app/vi2zh.js').read_text(encoding='utf-8')
V = json.loads(re.search(r'window\.VI2ZH=(\{.*\});?\s*$', vsrc, re.S).group(1))

def norm(s):
    s = re.sub(r'[（(][^）)]*[）)]', ' ', (s or '').lower())
    s = re.sub(r'[.,;:!?“”‘’\]\[]+$', '', s).strip()
    return re.sub(r'\s+', ' ', s)

def zh_len(s):
    return len(s)

single = [e for e in ZV if len(e[1]) == 1]
multi = [e for e in ZV if len(e[1]) > 1]
with_ex = [e for e in ZV if e[6] and e[6][0]]
no_ex = [e for e in ZV if not (e[6] and e[6][0])]
print('ZV', len(ZV), 'single', len(single), 'multi', len(multi), 'with_ex', len(with_ex), 'no_ex', len(no_ex))

# phrase candidates
cand = collections.defaultdict(dict)
for e in ZV:
    for j, raw in enumerate((e[3] or '').split('；')):
        s = norm(raw)
        if not s: continue
        sy = s.split()
        if 1 <= len(sy) <= 4:
            cand[s].setdefault(e[1], (j, e))
print('unique phrases 1-4 syl', len(cand))
bylen = collections.Counter(len(k.split()) for k in cand)
print('by syllables', dict(sorted(bylen.items())))
print('candidate count distribution', collections.Counter(len(v) for v in cand.values()).most_common(15))
print('phrases with >=2 cand', sum(1 for v in cand.values() if len(v) >= 2))
print('VI2ZH', len(V))

# VI2ZH candidate types
def is_single_zh(w): return len(w)==1
v_single = sum(1 for k,lst in V.items() for w in lst if is_single_zh(w))
v_words = sum(len(lst) for lst in V.values())
print('VI2ZH words', v_words, 'single-char occurrences', v_single)
# how many VI2ZH entries are all single-char
all_single = sum(1 for lst in V.values() if lst and all(is_single_zh(w) for w in lst))
print('VI2ZH entries all single-char', all_single)
empty = sum(1 for lst in V.values() if not lst)
print('VI2ZH empty lists', empty)
# candidate quality: each VI2ZH word must exist in ZV bySimp; count multi vs single
# common Chinese char list: use HSK chars + maybe freq
hsk = set()
for line in (ROOT/'data/hsk_all.tsv').read_text(encoding='utf-8').splitlines():
    p=line.split('\t')
    if p and p[0]: hsk.add(p[0])
print('hsk words', len(hsk))
# count headwords in HSK
print('ZV headwords in HSK', sum(1 for e in ZV if e[1] in hsk))
print('single headwords in HSK', sum(1 for e in single if e[1] in hsk))
# examples: Chinese sentence contains headword
bad_ex = []
for e in ZV:
    ex=e[6]
    if ex and ex[0] and e[1] not in ex[0]:
        bad_ex.append(e)
print('examples not containing headword', len(bad_ex))
# examples that are just "这个字读作"
def is_meta(s):
    return bool(re.search(r'(这个字|读作|读音|字读|汉字|词语)', s))
meta = [e for e in ZV if e[6] and e[6][0] and is_meta(e[6][0])]
print('meta-ish examples', len(meta))
# write sample random
random.seed(7)
sample = random.sample(list(cand.items()), 80)
out=[]
out.append('single chars sample:')
for e in random.sample(single, 40):
    out.append(json.dumps(e, ensure_ascii=False))
out.append('\nmulti rare sample:')
for e in random.sample(multi, 40):
    out.append(json.dumps(e, ensure_ascii=False))
out.append('\nphrase sample:')
for k,v in sample:
    out.append(k+' => '+json.dumps(sorted(v.keys()), ensure_ascii=False)+'  AI='+json.dumps(V.get(k), ensure_ascii=False))
(ROOT/'data/audit_sample.txt').write_text('\n'.join(out), encoding='utf-8')
print('wrote audit_sample.txt')
