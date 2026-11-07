## 漢南辭典 v1.5.6

### 越南語→中文 AI 精排全量完成
- v1.5.5 起的 AI 精排（Index-Translate 35B）**全量跑完**：28,536 個多候選越南語詞全部完成排序去雜
  （耗時 98 分鐘，28,312 詞獲得 AI 名單，其餘為單一候選無需精排）
- 修正合併邏輯：AI 給出的名單即最終結果（垃圾候選已被 AI 剔除，不再回填）——
  `nước` 現在只出 水（此前會跟出一串生僻單字）；`sách` → 书、书籍、书本、图书；`yêu` → 爱、喜爱、恋、爱上
- 主對應行在 AI 名單之後僅補充多字詞候選，生僻單字不再出現

### 下載
| 平台 | 檔案 |
|---|---|
| Windows | `HanVietDict-setup.exe` |
| Android | `zhongviet-translate.apk` |
| 網頁版 | https://siqyin.github.io/zhongviet-translate-web/ |
