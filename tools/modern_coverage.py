import json, re, pathlib, csv
ROOT = pathlib.Path(r'D:/项目上下文归档/2026-11-7 汉南辞典/01_源码/hanviet-app')
src=(ROOT/'app/zhvi.js').read_text(encoding='utf-8')
ZV=json.loads(re.search(r'window\.ZV=(\[.*?\]);?\s*$',src,re.S).group(1))
modern=set()
for r in csv.DictReader((ROOT/'data/modern_chinese_words.tsv').open(encoding='utf-8'),delimiter='\t'):
    modern.add(r['词语'])
print('modern',len(modern))
zs=set(e[1] for e in ZV)
print('ZV headwords',len(zs))
print('modern in ZV',len(modern & zs), '%.1f%%'%(100*len(modern&zs)/len(modern)))
print('ZV in modern',len(modern & zs), '%.1f%%'%(100*len(modern&zs)/len(zs)))
# proposed filter: single char must be modern; multi-char 2 chars must be modern; 3+ chars allow modern or (clean & zipf>=2.5?)
# just count modern entries
keep=[e for e in ZV if e[1] in modern]
print('keep modern only',len(keep))
# multi 3+ not modern
from wordfreq import zipf_frequency
extra=[e for e in ZV if len(e[1])>=3 and e[1] not in modern and zipf_frequency(e[1],'zh')>=2.5]
print('extra 3+ zipf>=2.5',len(extra))
# examples coverage if keep modern
print('examples keep',sum(1 for e in keep if e[6]))
