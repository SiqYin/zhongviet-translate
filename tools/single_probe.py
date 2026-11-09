import json, re, pathlib, collections, random
from wordfreq import zipf_frequency
ROOT = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/01_源码/hanviet-app')
src = (ROOT/'app/zhvi.js').read_text(encoding='utf-8')
ZV = json.loads(re.search(r'window\.ZV=(\[.*?\]);?\s*$', src, re.S).group(1))
def norm(s):
    s = re.sub(r'[（(][^）)]*[）)]', ' ', (s or '').lower())
    s = re.sub(r'[.,;:!?“”‘’\]\[]+$', '', s).strip()
    return re.sub(r'\s+', ' ', s)
cand=collections.defaultdict(set)
for e in ZV:
    for raw in (e[3] or '').split('；'):
        s=norm(raw)
        if s and 1<=len(s.split())<=4: cand[s].add(e[1])
single=[(k,list(v)) for k,v in cand.items() if len(v)==1]
print('single',len(single))
random.seed(42)
sample=random.sample(single,150)
out=[]
for k,v in sample:
    w=v[0]
    out.append(f"{k}\t{w}\tzipf={zipf_frequency(w,'zh'):.2f}\tlen={len(w)}")
(ROOT/'data/single_cand_sample.txt').write_text('\n'.join(out),encoding='utf-8')
# stats
sing_w=[v[0] for k,v in single]
print('single candidate single-char',sum(1 for w in sing_w if len(w)==1))
print('single candidate multi-char',sum(1 for w in sing_w if len(w)>1))
print('zipf >=4',sum(1 for w in sing_w if zipf_frequency(w,'zh')>=4))
print('zipf <3',sum(1 for w in sing_w if zipf_frequency(w,'zh')<3))
