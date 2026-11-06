# V3 第二階段：WebPAC 館藏頁「離線解析」實驗

## 為什麼先做離線解析
目前沒有確認臺南市圖允許第三方程式批量請求館藏，也沒有找到對外開放的即時館藏 API。**本工具不發送網路請求**，只解析人工取得、存於電腦上的合法公開詳細館藏頁 HTML。這不是已完成的即時串接。

解析依據：市圖 WebPAC 詳細頁公開的表格欄位：條碼號、典藏館、目前所在館、索書號、館藏狀態、資料類型、附件、預約人數、備註、預約。

## 使用方式
在自己有權查看的公開館藏詳細頁，於瀏覽器手動儲存 HTML 檔案。不要下載或提供包含個人借閱帳戶資訊的登入頁。
在本機執行：

```bash
python scripts/parse_webpac_snapshot.py path/to/detail.html --isbn 9789861615929 --captured-at 2026-11-06T08:00:00Z --output /tmp/holdings.json
python -m unittest discover -s scripts -p 'test_parse_webpac_snapshot.py' -v
node scripts/holdings_rules.test.mjs
```

## 保守的結果判斷
- 「展覽用書(不外借)」「限館內閱覽」「參考資料區」等 → 不可外借。
- 「借出」→ 曾進入借閱流通，但目前不是在架，不能列為現在可借。
- 普通「在架」→ 從公開 HTML 無法直接證明可外借資格，程式填寫 borrowable=null，不得自動宣稱「可借」。
- 多個館藏逐冊分開處理；單一詳情頁可能有 2、3、4 頁，程式固定輸出 complete=false，不推斷全市總量。
- 手動 HTML 快照不是即時資料：source=manual-html-snapshot，沒有明確提供擷取時間時 checkedAt 為空；即使填時間也不標記為正式 API。
- 不包含自動登入、繞過驗證、代理池、批次下載或背景定期抓取。

## 下一步的實際阻礙
需要取得館方同意或官方 API／可使用的匯出方式，並驗證 HTML 實際結構。測試使用模擬 HTML 表格，能確認欄位解析程式正確，但**不能代表已通過真實線上館藏頁解析**。

如果館方同意，可以使用單本、低頻率的請求驗證，再依使用條件逐步建立後端快取；取得資料後才把自動推薦接進正式網站。

## 2026-11-06 實際公開頁面觀察
- 在市圖官方 [《看不見也沒關係》書目頁](https://lib.tnml.tn.edu.tw/webpac/content.cfm?at=&c0=and&current_page=1&it=&k0=9789862746530&lg=&list_num=10&lr=&m=ss&mid=1184861&mt=&pr=&py=&si=&sj=&t0=k) 可見「展覽用書(可外借)」「展覽用書(不外借)」「在架」「借出」等不同狀態，也有分館標記「閉館整修」。**不能把所有展覽用書當成不外借。**
- 頁面示例顯示 27 筆館藏、分 3 頁；目前測試樣本只轉錄其中 5 筆作為重現用的 HTML 表格。參考 `scripts/fixtures/catalog_public_observation.json`。
- 解析器現在會輸出 `reportedHoldingsCount`、`parsedPageCopyCount`、`paginationLikely`，並保留 `complete=false`。沒有取得完整各頁資料就不推斷全市「只有展示本」或「全部借出」。
- 實際 WebPAC **HTML 原始碼仍未取得**；透過網頁檢索可見的表格欄位和資料不能取代真實 DOM 結構測試。離線程式已在 GitHub Actions 通過 13 個解析測試和 17 個流通判斷測試。

## 2026-11-06 上傳 HTML 的真實結構驗證成功
收到《好忙的除夕》的實際儲存頁面後，確認書目 ID `960206`、ISBN `9789861615929`，頁面列出「館藏(71)」，第一頁實際有 10 筆館藏和 8 頁分頁。原始頁面包含表頭、`<td data-title="...">`、館藏狀態 `<span>` 及每冊預約數。

- [已去除點擊處理程式的真實頁面片段](../scripts/fixtures/webpac_saved_real_detail.html)
- [驗證案例](../scripts/test_parse_webpac_snapshot.py)：通過 ISBN、館藏 71 冊、當頁 10 筆、第一頁／八頁、展覽用書(不外借)、視障資料區在架但外借未知、閉館整修分館等檢查。
- 真實片段中 10 筆狀態包含 7 筆借出、2 筆在架、1 筆展覽用書(不外借)。只有 1 頁，無法推論另外 61 筆的狀態。
- 程式新增 `currentPageNumber` 與 `totalPagesReported`，便於未來在獲得資料介接許可後確認分頁是否已全部取得。
- 這是**HTML 離線解析成功**，不是**自動連線成功**，也不代表網站已能即時顯示館藏。未登入、不蒐集個資、不爬取全站。
