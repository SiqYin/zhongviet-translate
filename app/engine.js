/* 漢喃詞典 — 查詢與排序引擎（純函式，可在瀏覽器與 Node 中執行） */
(function (root) {
  "use strict";

  function deacc(s) {
    return s
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");
  }

  function norm(s) {
    return (s || "").normalize("NFC").toLowerCase().trim().replace(/\s+/g, " ");
  }

  var CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;

  // 同義詞組：用於「意思相近」的釋義查詢
  var SYN = [
    ["說", "講", "談", "言", "道"], ["看", "見", "望", "瞧", "視"], ["大", "巨", "宏"],
    ["小", "微", "細"], ["吃", "食", "嚐"], ["走", "行", "步行"], ["家", "屋", "宅", "房子"],
    ["國", "邦", "國家"], ["人", "民", "人類"], ["好", "佳", "良"], ["美", "麗", "漂亮"],
    ["快", "速", "迅速"], ["慢", "緩"], ["高", "崇"], ["多", "眾", "許多"], ["少", "寡"],
    ["新", "鮮"], ["舊", "古", "老"], ["錢", "財", "銀"], ["心", "意", "心情"],
    ["頭", "首"], ["眼", "目"], ["手", "掌"], ["腳", "足", "腿"], ["父", "爸爸", "父親"],
    ["母", "媽媽", "母親"], ["子", "兒", "孩子"], ["女", "女子", "婦女"], ["男", "男子"],
    ["水", "液"], ["火", "焰"], ["山", "嶺"], ["河", "江"], ["路", "道", "途"],
    ["買", "購"], ["賣", "售"], ["學", "習"], ["教", "育"], ["問", "詢"],
    ["答", "回", "覆"], ["開", "啟"], ["關", "閉"], ["給", "予"], ["拿", "取", "持"],
    ["做", "作", "為"], ["想", "思", "念"], ["怕", "懼"], ["愛", "戀"], ["恨", "怨"],
    ["真", "實"], ["假", "偽"], ["冷", "寒"], ["熱", "暖"], ["亮", "明"], ["暗", "黑"]
  ];

  var SYN_INDEX = {};
  SYN.forEach(function (g) {
    g.forEach(function (w) {
      (SYN_INDEX[w] = SYN_INDEX[w] || []).push(g);
    });
  });

  function expand(q) {
    var out = [];
    (SYN_INDEX[q] || []).forEach(function (g) {
      g.forEach(function (w) { if (w !== q) out.push(w); });
    });
    return out;
  }

  function index(raw) {
    return raw.map(function (r) {
      return {
        r: r,
        vl: r.v.toLowerCase(),
        vd: deacc(r.v.toLowerCase()),
        zl: (r.z || "").toLowerCase(),
        sl: (r.s || "").toLowerCase(),
        syl: r.v.trim().split(/\s+/).length
      };
    });
  }

  // 國語字評分
  function scoreVi(e, q, qd) {
    var v = e.vl, vd = e.vd, syl = v.split(" "), s = -1;
    if (v === q) s = 1200;                              // 完全相等
    else if (vd === qd) s = 880;                        // 省略聲調後相等
    else {
      var idx = -1;
      for (var i = 0; i < syl.length; i++) {
        if (syl[i] === q || deacc(syl[i]) === qd) { idx = i; break; }
      }
      if (idx === 0) s = 820 - Math.max(0, syl.length - 2) * 12;        // 詞首音節
      else if (idx > 0) s = 720 - idx * 8 - Math.max(0, syl.length - 2) * 12; // 詞中音節
      else if (v.indexOf(q) === 0) s = 640;             // 前綴
      else if (vd.indexOf(qd) === 0) s = 600;
      else if (v.indexOf(q) > -1) s = 520;              // 子串
      else if (vd.indexOf(qd) > -1) s = 470;
    }
    if (s < 0) return -1;
    if (syl.length === 1) s += 120;                     // 單音節詞條優先
    s -= Math.max(0, syl.length - 1) * 6;               // 詞越長越靠後
    if (e.r.t === 2) s -= 240;                          // 只有讀音的字條排在詞條之後
    return s;
  }

  // 漢字釋義評分
  function scoreZh(e, qz, qs, syn) {
    var z = e.zl, m = e.sl, s = -1;
    if (!z) {
      if (e.r.t === 2 && e.r.n === qz) return 980;     // 字條：字本身命中
      return -1;
    }
    // 去掉詞形標記，避免「〔馬〕」這類寫法影響匹配
    z = z.replace(/[〔〕【】\[\]]/g, "");
    m = m.replace(/[〔〕【】\[\]]/g, "");
    if (z === qz || m === qs) s = 1200;
    else if (z.indexOf(qz) === 0 || m.indexOf(qs) === 0) s = 900;
    else {
      var i = z.indexOf(qz), j = m.indexOf(qs);
      var pos = i > -1 ? i : j;
      if (pos > -1) s = 820 - Math.min(pos, 10) * 10;
      else {
        for (var k = 0; k < syn.length; k++) {
          if (z.indexOf(syn[k]) > -1 || m.indexOf(syn[k]) > -1) { s = 640; break; }
        }
      }
    }
    if (s < 0) return -1;
    if (e.r.nf === qz || e.r.nfs === qs) s += 80;      // 查詢字正好是詞頭
    var first = z.split(/[；;，,、]/)[0];
    if (first === qz || first === qs) s += 60;          // 第一個義項就是查詢字
    s -= Math.min(z.length, 40) * 0.6;                  // 釋義越短越靠前
    return s;
  }

  function search(rawIndex, query, limit) {
    var q = norm(query);
    if (!q) return [];
    limit = limit || 200;
    var hits = [], i;
    if (CJK.test(q)) {
      var syn = expand(q);
      for (i = 0; i < rawIndex.length; i++) {
        var s = scoreZh(rawIndex[i], q, q, syn);
        if (s > -1) hits.push([s, rawIndex[i]]);
      }
    } else {
      var qd = deacc(q);
      for (i = 0; i < rawIndex.length; i++) {
        var t = scoreVi(rawIndex[i], q, qd);
        if (t > -1) hits.push([t, rawIndex[i]]);
      }
    }
    hits.sort(function (a, b) {
      var ca = a[1].r.t === 2 ? 1 : 0, cb = b[1].r.t === 2 ? 1 : 0;
      if (ca !== cb) return ca - cb;                    // 先詞條，後純讀音字條
      if (b[0] !== a[0]) return b[0] - a[0];
      if (a[1].r.f !== b[1].r.f) return a[1].r.f - b[1].r.f;
      return a[1].r.v.length - b[1].r.v.length;
    });
    return hits.slice(0, limit).map(function (h) { return h[1].r; });
  }

  var api = { deacc: deacc, norm: norm, index: index, search: search, expand: expand, CJK: CJK };

  // ---- IDS 部件拆解 → 中文描述 ----
  var IDS_OPS = {
    "⿰": ["左右", 2], "⿱": ["上下", 2], "⿲": ["左中右", 3], "⿳": ["上中下", 3],
    "⿴": ["全包圍", 2], "⿵": ["上三包", 2], "⿶": ["下三包", 2], "⿷": ["左三包", 2],
    "⿸": ["左上包", 2], "⿹": ["右上包", 2], "⿺": ["左下包", 2], "⿻": ["重疊", 2]
  };

  function consume(s, i) {
    var def = IDS_OPS[s[i]];
    var need = def[1], j = i + 1, n = 0;
    while (j < s.length && n < need) {
      if (IDS_OPS[s[j]]) { j = consume(s, j)[1]; } else { j++; }
      n++;
    }
    return [s.slice(i, j), j];
  }

  function describeIds(ids) {
    if (!ids) return null;
    var def = IDS_OPS[ids[0]];
    if (!def) return { name: "", parts: [ids] };
    var parts = [], i = 1, need = def[1];
    while (i < ids.length && parts.length < need) {
      if (IDS_OPS[ids[i]]) {
        var r = consume(ids, i);
        parts.push({ sub: r[0] });
        i = r[1];
      } else {
        parts.push({ ch: ids[i] });
        i++;
      }
    }
    return { name: def[0], parts: parts };
  }

  function idsText(ids) {
    var d = describeIds(ids);
    if (!d) return "";
    if (!d.name) return ids;
    return d.parts.map(function (p) {
      if (p.ch) return p.ch;
      var inner = describeIds(p.sub);
      return inner && inner.name ? "（" + inner.name + "： " + inner.parts.map(function (x) { return x.ch || x.sub; }).join(" ＋ ") + "）" : p.sub;
    }).join(" ＋ ");
  }

  api.describeIds = describeIds;
  api.idsText = idsText;

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.Engine = api;
})(typeof window !== "undefined" ? window : null);
