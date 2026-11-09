import json, re, pathlib, collections
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
print('phrases',len(cand))
# viet74k
v74=set()
for line in (ROOT.parent.parent/'02_数据管线/原始数据/viet74k.txt').read_text(encoding='utf-8', errors='replace').splitlines():
    s=norm(line)
    if s: v74.add(s)
print('viet74k',len(v74))
hit=[k for k in cand if k in v74]
print('phrases in viet74k',len(hit), '%.1f%%'%(100*len(hit)/len(cand)))
bylen=collections.Counter(len(k.split()) for k in hit)
print('hit by len',dict(sorted(bylen.items())))
print('not hit sample', [k for k in list(cand)[:50] if k not in v74][:20])
# NOMDATA
nomjs=(ROOT/'app/nom.js').read_text(encoding='utf-8')
print('nom.js head', nomjs[:200])
m=re.search(r'window\.NOMDATA=(\[.*?\]);?\s*$',nomjs,re.S)
if m:
    ND=json.loads(m.group(1)); print('NOMDATA',len(ND),ND[:3])
    nd=set(norm(x[0]) for x in ND if x and x[0])
    hit2=[k for k in cand if k in nd]
    print('phrases in NOMDATA',len(hit2))
