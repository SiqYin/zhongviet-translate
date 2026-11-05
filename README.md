# 漢喃詞典 · Hán Nôm Dictionary

面向中文母語者的**漢語—越南語**雙向詞典，附字喃字形。離線優先，純 HTML/CSS/JS，可打包為 Windows 桌面版與 Android App。

## 功能

### 查詞

| 輸入 | 結果 |
|---|---|
| 中文詞（簡體或繁體） | 該詞的越南語實際用詞、拼音、注音、繁體、**漢越音**，以及「以它開頭／包含它」的相關詞族 |
| 越南語（可省略聲調） | 對應的中文詞，按義項貼合度排序 |
| 字喃 | 暫不支援（見「尚未完成」） |

例：輸入 `鸡` → `gà`，並列出 公鸡 gà trống、小鸡 gà con、鸡肉 thịt gà……
輸入 `gà` → 鸡 jī、公鸡 gōng jī、母鸡 mǔ jī……

### AI 翻譯

「翻譯」頁支援四種方向，共用一組控制：

- 中 → 越（簡體或繁體）
- 越 → 中（簡體或繁體）

譯文會按詞切分，**滑鼠移到任一個詞上（手機點一下）就彈出該詞的詞典釋義**，可直接跳轉完整詞條。

- 中文用最大匹配分詞，詞表就是詞典本身（11.5 萬詞頭）
- 越南語按音節合併成詞（`Hôm qua`、`đi làm`、`bị sốt`）
- 預設接 [bilibili/Index-Translate](https://github.com/bilibili/Index-Translate) 的免費公共介面（相容 OpenAI 協議，Apache-2.0），可在「翻譯設定」換成任何自架端點，如 `http://127.0.0.1:8000/v1`
- 服務不通時可切「詞庫逐詞直譯」，純離線，按詞典一詞一詞對照

## 規模

- **詞條 115,243 條**：中文詞頭 + 拼音 + 越南語義項（最多 5 條）
- 112,934 條有漢越音，9,900 條有字喃字形
- **10,087 條**已完成 AI 校正（HSK 5,000 + 斯瓦迪士 + 全部單字）
- 查詢索引：簡體、繁體雙向

## 目錄

```
hanviet-app/
├─ app/                  # 前端，無框架、無需建置
│  ├─ index.html
│  ├─ style.css
│  ├─ app.js             # 查詞與排序
│  ├─ translate.js       # 翻譯頁、分詞、詞語彈窗
│  ├─ zhvi.js            # 詞庫（由工具生成，勿手改）
│  └─ nom.js             # 越南語 → 字喃
├─ electron/main.js      # Windows 外殼
├─ capacitor.config.json # Android 外殼
├─ tools/
│  ├─ build_zhvi.py          # CVDICT → app/zhvi.js，含 AI 校正套用
│  ├─ ai_correct.py          # 呼叫 Index-Translate 批量校正義項
│  ├─ make_ai_fix.py         # 校正結果 → data/ai_fix.json + 審閱報告
│  ├─ check_swadesh.js       # 斯瓦迪士核心詞抽查
│  ├─ ui_test.js             # Puppeteer 介面回歸測試
│  └─ opencc/                # OpenCC 繁簡表（Apache-2.0）
└─ data/                 # 中間資料與校正快取
```

## 重新生成

```bash
python tools/build_zhvi.py        # 產出 app/zhvi.js（約 12MB）
```

需要 `../cvdict.u8`、`../Unihan_Readings.txt`、`../hanviet.csv`、`data/hsk_all.tsv`。

## 校正管線

詞條內容由 CVDICT（CC BY-SA 4.0）轉出，原始資料有選義偏差、誇張釋義、多音字混義等問題，
用 Index-Translate 逐詞校一輪：

```bash
# 1. 批量取「最常用越南語對應詞」，結果快取，可中斷續跑
python tools/ai_correct.py --tier all --workers 3

# 2. 產生 data/ai_fix.json 與審閱報告 data/ai_fix_report.tsv
python tools/make_ai_fix.py

# 3. 重跑 build_zhvi.py 套用
python tools/build_zhvi.py
```

`--tier core` 只跑 HSK 5,000 + 斯瓦迪士核心詞，`--tier single` 只跑單字。

落地時有四道守門，避免 AI 把正確的內容改壞：

1. 值等於該字漢越音 → 略過（模型有時直接給漢字音，如 活 → Hoạt）
2. 罕見字（CJK 擴展 A/B 區）→ 略過（模型只能靠字形猜，實測大量誤判）
3. 姓氏義（裸的 `họ`）→ 不提升為主義
4. 值含中文、過長、帶括號或斜線 → 丟棄

全部改動都寫進 `data/ai_fix_report.tsv`，可逐條覆核。

## 執行

```bash
# 瀏覽器預覽
python -m http.server 5173 --directory app

# Windows 桌面版
npm install
npm start

# Windows 安裝檔
npm run dist:win        # release/HanVietDict-0.1.0-setup.exe

# Android
npx cap sync android
npx cap open android    # 在 Android Studio 產生 APK
```

## 資料來源與授權

- 中越詞條：**CVDICT**（CC BY-SA 4.0）
- 字喃：**chunom.org / old.chunom.org**（Chunom Project），授權洽談中
- 繁簡轉換：**OpenCC**（Apache-2.0）
- 漢越音：Unihan `kVietnamese` + `ph0ngp/hanviet-pinyin-wordlist` + 人工校正
- 翻譯模型：**Index-Translate**（Apache-2.0）

CVDICT 帶 CC BY-SA，公開發布需署名並以相同方式共享。chunom 部分見 `NOTICE.md`，
**在取得書面同意前，本倉庫請保持 private。**

## 尚未完成

- 字喃作為查詢輸入
- 例句（chunom 語料 3,234 行尚未接入）
- 漢越音仍有少量多音字錯讀，需逐字校（AI 對漢越音約八成可靠，不宜整體替換）
- 11 萬詞條的 AI 校正仍在分批推進，非 HSK 的長尾詞尚未覆蓋
- iOS
