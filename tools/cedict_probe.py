import json, re, pathlib, collections
from wordfreq import zipf_frequency
ROOT = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/01_源码/hanviet-app')
CED = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/02_数据管线/原始数据/cedict.txt')
src = (ROOT/'app/zhvi.js').read_text(encoding='utf-8')
ZV = json.loads(re.search(r'window\.ZV=(\[.*?\]);?\s*$', src, re.S).group(1))

# parse cedict: trad simp [pinyin] /gloss/
meta = {}
pat = re.compile(r'^(\S+) (\S+) \[([^\]]*)\] /(.*)/$')
for line in CED.read_text(encoding='utf-8').splitlines():
    m=pat.match(line)
    if not m: continue
    trad,simp,py,gloss=m.groups()
    g=gloss.lower()
    flags=set()
    if 'radical in' in g or 'kangxi radical' in g or 'component in chinese characters' in g:
        flags.add('radical')
    if 'variant of' in g or 'old variant' in g or 'archaic variant' in g:
        flags.add('variant')
    if 'cantonese' in g or 'dialect' in g or 'taiwanese' in g or 'hokkien' in g or 'colloquial' in g:
        flags.add('dialect')
    if '(old)' in g or 'archaic' in g or 'literary' in g or 'classical' in g:
        flags.add('archaic')
    if g.startswith('surname') or ' surname' in g:
        flags.add('surname')
    d=meta.setdefault(simp, {'flags':set(),'glosses':[]})
    d['flags'] |= flags
    d['glosses'].append(gloss)

def flags_of(e):
    return meta.get(e[1],{}).get('flags',set())

cnt=collections.Counter()
for e in ZV:
    fl=flags_of(e)
    for f in fl: cnt[f]+=1
    if not fl: cnt['clean']+=1
print('ZV',len(ZV),'cedict keys',len(meta))
print('flags',dict(cnt))
# cross-tab with zipf
for th in [0,2,2.5,3,3.5,4,4.5,5]:
    keep=[e for e in ZV if not flags_of(e) and zipf_frequency(e[1],'zh')>=th]
    print('clean & zipf>=',th,len(keep))
# specific
for w in ['咁','偌','乃','恁般','若然','信然','倘然','亻','氵','侴','歊','然','这样','如此','水','书','爱','走','去','行','人']:
    e=next((x for x in ZV if x[1]==w),None)
    print(w, 'flags=', sorted(meta.get(w,{}).get('flags',[])), 'zipf=', round(zipf_frequency(w,'zh'),2), 'inZV=', bool(e), 'sense=', e[3][:50] if e else '')
# sample flagged entries
out=[]
for e in ZV:
    fl=flags_of(e)
    if fl:
        out.append(f"{e[1]}\t{','.join(sorted(fl))}\t{e[2]}\t{e[3][:70]}")
(ROOT/'data/flagged_sample.txt').write_text('\n'.join(out[:500]),encoding='utf-8')
print('flagged sample written',len(out))
