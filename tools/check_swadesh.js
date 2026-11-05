const fs = require("fs"), vm = require("vm");
const ctx = { window: {} }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + "/../app/zhvi.js", "utf8"), ctx);
const ZV = ctx.window.ZV;

const ZH = ["我","你","他","我们","你们","他们","这","那","这里","那里",
"谁","什么","哪里","什么时候","怎么","不","全部","多","一些","少",
"其他","一","二","三","四","五","大","长","宽","厚","重",
"小","短","窄","薄","女人","男人","人","小孩","妻子","丈夫",
"母亲","父亲","动物","鱼","鸟","狗","虱子","蛇","虫","树",
"森林","棍子","水果","种子","叶子","根","树皮","花","草","绳子",
"皮肤","肉","血","骨头","脂肪","蛋","角","尾巴","羽毛","头发",
"头","耳朵","眼睛","鼻子","嘴","牙齿","舌头","指甲","脚","腿",
"膝盖","手","翅膀","肚子","肠子","脖子","背","乳房","心","肝",
"喝","吃","咬","吸","吐","呕吐","吹","呼吸","笑","看",
"听","知道","想","闻","怕","睡","活","死","杀","打斗",
"打猎","打","切","分","刺","抓","挖","游泳","飞","走",
"来","躺","坐","站","转","掉","给","拿","挤","擦",
"洗","擦干","拉","推","扔","绑","缝","数","说","唱",
"玩","浮","流","冻","肿","太阳","月亮","星星","水","雨",
"河","湖","海","盐","石头","沙子","灰尘","土","云","雾",
"天空","风","雪","冰","烟","火","灰","烧","路","山",
"红","绿","黄","白","黑","夜","白天","年","暖","冷",
"满","新","旧","好","坏","烂","脏","直","圆","尖",
"钝","滑","湿","干","对","近","远","右","左","在",
"里","和","和","如果","因为","名字"];

const bySimp = new Map(), byTrad = new Map();
ZV.forEach((e, i) => { if (!bySimp.has(e[1])) bySimp.set(e[1], i); if (!byTrad.has(e[0])) byTrad.set(e[0], i); });
const SPLIT = /[^0-9a-zàáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]+/;
const tok = s => (s || "").toLowerCase().split(SPLIT).filter(Boolean);
const senses = e => (e[3] || "").split("；").filter(Boolean);

let pass = 0, fail = [], rows = [];
ZH.forEach((w, idx) => {
  const i = bySimp.has(w) ? bySimp.get(w) : byTrad.has(w) ? byTrad.get(w) : -1;
  if (i < 0) { fail.push([idx + 1, w, "無詞條"]); rows.push([idx + 1, w, "", "", "", "", 0, "無詞條"]); return; }
  const e = ZV[i];
  const vi = senses(e)[0] || "";
  const hv = e[4] || "";
  let fam = 0;
  for (let k = 0; k < ZV.length; k++) {
    if (k === i) continue;
    if (ZV[k][1].length > 6) continue;
    if (ZV[k][1].indexOf(w) === -1 && ZV[k][0].indexOf(w) === -1) continue;
    if (tok(ZV[k][3]).indexOf(tok(vi)[0] || "") > -1) fam++;
  }
  const problems = [];
  if (!vi) problems.push("無越語");
  if (!hv) problems.push("無漢越音");
  if (/^họ \[/.test(vi)) problems.push("姓氏義");
  if (vi.length > 60) problems.push("釋義過長");
  if (fam < 2) problems.push("相關詞少");
  if (problems.length) fail.push([idx + 1, w, problems.join("/") + " → " + vi]);
  else pass++;
  rows.push([idx + 1, w, e[2], hv, vi, e[5] || "", fam, problems.join("/")]);
});

const head = "序\t中文\t拼音\t漢越音\t越語\t字喃\t相關詞\t問題";
fs.writeFileSync(__dirname + "/../data/swadesh_report.tsv", head + "\n" + rows.map(r => r.join("\t")).join("\n"), "utf8");
console.log("總計", ZH.length, "通過", pass, "問題", fail.length);
fail.slice(0, 40).forEach(f => console.log("  #" + f[0], f[1], f[2]));
