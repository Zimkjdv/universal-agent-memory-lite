# 安全、隱私與風險

狀態：完整安全設計。2026-10-22 雛形已具備路徑／解析防護、合作鎖、hash、備份及 checkpoint 中斷偵測；尚未完成完整安全驗收。Local-first 不等於雲端 Agent 讀取後資料永不離開電腦。

本輪限制：沒有自動 repair 或 stale-lock 接管；備份／Registry 依使用者目錄繼承權限，尚無完整 Windows ACL 設定與驗收。明確寫入命令沒有完整 diff/proposal UI。初始新檔以同目錄暫存檔＋hard link 發布，依賴本機檔案系統；不支援時回報失敗，不改用可能覆寫的替代流程。雛形秘密檢查只辨識少數常見模式，不能當成完整 DLP。

## 信任邊界

Manifest、Markdown、索引、路徑及歷史測試命令均是不可信資料。只有使用者核准的本機 Registry／checkout grant 決定工具允許範圍。任何筆記不能提升指令優先級、擴大權限或要求自動執行命令。

限制在授權 UAML 子樹，不隱含讀取整個 Vault；所有搜尋與讀寫入口套用同一政策。realpath／junction／symlink 必須檢查根目錄，不能只做字串前綴。防護不代替 OS ACL，無法隔離本來有權直接讀檔的程序。

## 安全寫入契約

1. 驗證 Binding、身份與寫入子範圍。
2. 讀取目前位元組及 expected SHA-256。
3. 驗證 Schema、路徑、大小及敏感內容。
4. 產生可審閱 diff；依使用者已授權操作套用，不重複要求例行批准。
5. 取得資源鎖，在鎖內重讀並比較 hash。
6. 保存原內容受限備份；未通過檢查的新內容不能先落入備份。
7. 在目標同目錄準備暫存檔、flush，再替換目標。
8. 驗證結果後更新衍生索引；失敗不能回報成功。

替換可用 [os.replace](https://docs.python.org/3/library/os.html#os.replace) 等原語，但同檔案系統、Windows 檔案佔用、耐斷電與多檔一致性仍需各自驗證，不照搬 POSIX 保證。

安全 YAML 解析限制 tags／aliases 等；不得使用不安全物件載入。參考 [PyYAML 說明](https://pyyaml.org/wiki/PyYAMLDocumentation)。不自動抓取遠端 schema、連結或引用。

## 並行與鎖

- 同機合作 UAML 程序：lock＋expected hash，避免 lost update。
- 同筆記同鎖；新增去重在共同鎖內再次檢查。
- Registry 更新採整份鎖；多 Agent 改 Binding 也須檢查舊 hash。
- 鎖有 owner token，必要時驗證持有者；不能只因過了固定秒數就強制刪鎖。
- 無法安全證明鎖失效時，停寫並提供明確復原流程。
- Obsidian／同步程式可能不遵守 UAML 鎖；仍存在最後檢查到替換間的競態，須備份、前後檢查及保留衝突提案，不宣稱完全消除。
- v0.1 建議保證本機檔案系統的合作寫入，不提供跨機分散式鎖或網路磁碟一致性。

## 多檔 checkpoint 與復原

以 journal 記錄舊 hash、新 snapshot_id 及預定檔案；準備 State/Handoff 與備份，替換 Markdown，最後公布 checkpoint.json。讀者必須檢查兩個 hash 及 snapshot_id，不把混合版本當成完整保存。

中斷後偵測 checkpoint 不一致，提供完成／回復方案。復原前再次核對當前 hash；若使用者在當機後修改檔案，不可直接覆蓋。保留可辨識的原檔、暫存與提案，直到安全完成復原。備份清理須有明確政策，不默默刪除使用者資料。

Repo 與 Vault 不建立跨磁碟交易。知識保存失敗獨立回報，不因其失敗而回滾程式碼或假稱完整保存。

## 敏感內容

不採集環境變數全文、憑證檔、完整對話或無限制工具輸出。檢查私鑰、已知 Token 模式、URL userinfo 等，命中時拒絕寫入並遮罩診斷，不重印秘密。公開 Manifest 不含本機路徑或私人帳號資料。

Registry／備份限制目前使用者，不放寬 ACL。備份舊內容前同樣考慮原檔可能已有敏感資料；不得把私密備份轉存公開位置。

秘密偵測不可能保證識別所有未知憑證。最小收集、欄位限制與差異審閱仍是主要控制。保存驗收證據時使用假憑證及合成資料。

## 主要風險表

| 風險 | 防範／限制 |
| --- | --- |
| Agent 未啟動恢復 | 明確入口、來源證據、真實新對話驗收 |
| Fork 複製 ID | 首次 checkout grant，不憑 ID 授權 |
| Vault 權限不足 | 唯讀降級，最小範圍配置 |
| 多副本分歧 | 顯式候選，不依 mtime 猜權威 |
| 中文／版本去重錯誤 | Unicode、條件檢查、近似只提案 |
| 過時摘要 | Git／實際檔案優先 |
| 自我參照 Commit | 保存前程式碼基準及清楚排除範圍 |
| 外部編輯競態 | expected hash、備份、衝突保留，限制保證 |
| 跨機同步競態 | 使用同步完成穩定副本，無分散式承諾 |
| Prompt injection | 資料與指令分離，工具不執行筆記 |
| 過度自動化 | 事件驅動、有界讀取、無常駐服務 |

## 必要驗證

Windows ACL、junction/symlink、檔案佔用、鎖持有、並行寫入、半完成 checkpoint、手動修改後復原、惡意筆記與假 Token、未知 Schema。完整案例見 [驗收計畫](ACCEPTANCE-TESTS.md)。
