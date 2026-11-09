import json, re, pathlib, collections
from wordfreq import zipf_frequency
ROOT = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/01_源码/hanviet-app')
src = (ROOT/'app/zhvi.js').read_text(encoding='utf-8')
ZV = json.loads(re.search(r'window\.ZV=(\[.*?\]);?\s*$', src, re.S).group(1))
words = [e[1] for e in ZV]
freq = {w: zipf_frequency(w, 'zh') for w in set(words)}
print('unique headwords', len(freq))
for t in [0,1,2,2.5,3,3.5,4,4.5,5,5.5,6]:
    print('zipf >=', t, sum(1 for v in freq.values() if v>=t))
for w in ['咁','偌','乃','然','恁般','亻','氵','侴','歊','這樣','这样','如此','那么','水','书','書','爱','愛','走','去','行','若然','信然','倘然','之乎者也']:
    print(w, zipf_frequency(w,'zh'))
# examples of low/high
print('\nlow freq single chars sample:')
singles=[e for e in ZV if len(e[1])==1]
for e in sorted(singles, key=lambda e: freq[e[1]])[:30]: print(e[1], round(freq[e[1]],2), e[2], e[3][:40])
print('\nhigh freq single chars sample:')
for e in sorted(singles, key=lambda e: -freq[e[1]])[:30]: print(e[1], round(freq[e[1]],2), e[2], e[3][:40])
print('\nmulti low freq sample:')
multis=[e for e in ZV if len(e[1])>1]
for e in sorted(multis, key=lambda e: freq[e[1]])[:30]: print(e[1], round(freq[e[1]],2), e[2], e[3][:40])
print('\nmulti headwords zipf<2', sum(1 for e in multis if freq[e[1]]<2))
print('multi headwords zipf<2.5', sum(1 for e in multis if freq[e[1]]<2.5))
print('multi headwords zipf<3', sum(1 for e in multis if freq[e[1]]<3))
