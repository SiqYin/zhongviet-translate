# 漢喃詞典 · Hán Nôm Dictionary

面向中文母語者的**越南語—字喃—漢語**三向對照詞典。離線優先，單一網頁程式碼，可打包為 Windows 桌面版與 Android App。

## 目前狀態

- 總計 **19,348 條**，分兩層：
  - **詞條層 2,518 條**：889 個單字 + 1,629 個詞，每條有國語字、字喃、繁體中文釋義
  - **字條層 16,830 條**：只有字喃字形與越南語讀音，尚無中文釋義
- 單字另有：部首、筆畫、Grade、詞頻、IDS 部件拆解（中文結構描述）
- 排序時詞條永遠排在字條之前
- 查詢：國語字（可省略聲調）／簡體漢字／繁體漢字
- 排序：單音節完全對應最優先 → 詞首音節 → 詞中含該音節 → 子串

## 目錄

```
hanviet-app/
├─ app/                 # 前端（純 HTML/CSS/JS，無框架、無需建置）
│  ├─ index.html
│  ├─ style.css
│  ├─ app.js            # 查詢與排序引擎
│  └─ data.js           # 由工具生成，勿手改
├─ electron/main.js     # Windows 外殼
├─ capacitor.config.json# Android 外殼
├─ tools/
│  ├─ build_entries.py      # 合併 dict.csv + standard-list
│  ├─ enrich_chars_fast.py  # 抓單字部首／IPA／IDS
│  ├─ build_data.py         # 合併翻譯 → app/data.js
│  └─ opencc/               # OpenCC 繁→簡表（Apache-2.0）
├─ translate/           # 英文釋義 → 繁體中文 的翻譯記憶
└─ data/                # 中間資料
```

## 重新生成資料

```bash
python tools/build_entries.py
python tools/enrich_chars_fast.py     # 需要網路，約 3 分鐘
python tools/build_data.py            # 產出 app/data.js
```

翻譯以 `translate/src_*.txt`（編號 + 英文）與 `translate/zh_*.txt`（編號 + 繁中）成對保存，
之後接 AI 翻譯時，只要替換 `zh_*.txt` 並重跑 `build_data.py` 即可。

## 執行

```bash
# 瀏覽器預覽
python -m http.server 5173 --directory app

# Windows 桌面版（開發）
npm install
npm start

# Windows 安裝檔
npm run dist:win        # 產出 release/HanVietDict-0.1.0-setup.exe

# Android
npm install
npx cap add android
npx cap sync android
npx cap open android    # 在 Android Studio 產生 APK / AAB
```

## 查詢規則

| 輸入 | 行為 |
|---|---|
| `nước` / `nuoc` | 國語字查詢，聲調可省略 |
| `水` / `水`（繁） | 釋義包含該字，或同義詞組命中 |
| `học sinh` | 多音節詞組查詢 |

排序分數（由高到低）：完全相等 > 單音節詞條 > 詞首音節 > 詞中音節 > 子串；
同分時依詞頻、詞長排序。

## 資料來源

- 詞條、字喃、釋義：**chunom.org / old.chunom.org**（Chunom Project）
- 繁簡轉換表：**OpenCC**（Apache License 2.0）

資料授權仍在與 Chunom Project 團隊確認中，見 `NOTICE.md`。**在取得書面同意前，本倉庫請保持 private。**

## 尚未完成

- 字喃本身作為查詢輸入（目前不支援）
- 例句（來源語料 3,234 行尚未接入）
- 釋義的人工審校與 AI 翻譯管線
- iOS
