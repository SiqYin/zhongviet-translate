import json,re,html,pathlib,urllib.parse,urllib.request,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=pathlib.Path(__file__).resolve().parent.parent
E=json.load(open(ROOT/'data'/'entries_raw.json',encoding='utf-8'))
chars=[e for e in E if e['is_char']]
chars.sort(key=lambda e:e.get('freq_i',999999))
chars=[e['nom'] for e in chars[:220]]
UA={'User-Agent':'Mozilla/5.0 (compatible; HanVietDictBuilder/0.1)'}
def clean(s):
    s=re.sub(r'<[^>]+>','',s); s=html.unescape(s).replace('\u2009','').strip()
    return re.sub(r'\s+',' ',s)
def one(ch):
    url='https://old.chunom.org/pages/'+urllib.parse.quote(ch)+'/'
    h=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=8).read().decode('utf-8','ignore')
    rec={}
    m=re.search(r'\[([^\[\]]+)\]\s*<sup>north</sup>',h)
    if m: rec['ipa_n']=clean(m.group(1))
    m=re.search(r'\[([^\[\]]+)\]\s*<sup>south</sup>',h)
    if m: rec['ipa_s']=clean(m.group(1))
    m=re.search(r'class="ids-string">([^<]+)<',h)
    if m: rec['ids']=clean(m.group(1))
    m=re.search(r'Strokes</td><td>(\d+)</td>',h)
    if m: rec['strokes']=int(m.group(1))
    return ch,rec
out={}
with ThreadPoolExecutor(max_workers=12) as ex:
    futs={ex.submit(one,c):c for c in chars}
    for f in as_completed(futs):
        try:
            ch,rec=f.result(); out[ch]=rec
        except Exception: pass
json.dump(out,open(ROOT/'data'/'char_meta.json','w',encoding='utf-8'),ensure_ascii=False)
print('meta',len(out),'ids',sum(1 for v in out.values() if v.get('ids')),flush=True)
