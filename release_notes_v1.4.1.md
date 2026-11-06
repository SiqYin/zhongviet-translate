## 漢南辭典 v1.4.1

### 修復
- **Android 桌面圖標不更新**：圓形圖標資源的命名空間寫錯（`schemas/android.com`），啟動器取圓形圖標失敗就回退顯示舊緩存。已修正，桌面圖標恢復為蓮花徽章
- **自適應圖標白蓮過大**：前景白蓮從畫布 47% 縮至 32%（對應可視區約 47%），與 Windows／網頁圖標比例一致
- **無法覆蓋更新（簽名不兼容）**：此前每個版本的 APK 都由 CI 臨時生成調試簽名，簽名各不相同，故舊版無法覆蓋安裝。現已統一為固定的正式簽名密鑰
- **版本號從未遞增**：`versionCode` 一直停在 5、`versionName` 停在 1.2.2。現已升為 `versionCode 8` / `versionName 1.4.1`

### 升級說明
- **從 1.4.0 及更早版本升級到 1.4.1，需先卸載舊版再安裝**（簽名變更所致，僅此一次）。
  詞典不儲存用戶數據，卸載無損失；設定項（界面語言等）重裝後需重新選擇
- **從 1.4.1 起可直接覆蓋更新**，無需再卸載
- Windows 端不受影響（NSIS 安裝包不校驗簽名，appId 未變），直接覆蓋安裝即可

### 下載
| 平台 | 檔案 |
|---|---|
| Windows | `HanVietDict-setup.exe` |
| Android | `zhongviet-translate.apk` |
| 網頁版 | https://siqyin.github.io/zhongviet-translate-web/ |
