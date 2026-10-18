# 產品需求規格

狀態：Phase 2 草案。正式名稱 Universal Agent Memory Lite（UAML）；目標首版 v0.1.0。早期 Local Memory Lite、Agent-Agnostic Memory、UAML V1/V2 名稱不構成舊版相容需求。

## 產品目標與需求優先序

讓不同 Coding Agent 在新對話、不同 Repository、不同電腦及模型間，恢復已持久化的開發上下文與可重用技術知識。當前使用者要求與正式需求優先於歷史探索建議；Git、實際程式碼與當前驗證優先於過時摘要。

首批環境：Windows 11、Codex Windows 桌面版、Claude Code、Git／GitHub、Obsidian 或本地 Markdown Vault。預留 Gemini CLI、Cursor 與其他 OS，禁止綁定模型版本。

## 使用情境

1. 同一 Agent 開新對話，找到記憶並核對實際狀態。
2. Codex 與 Claude Code 雙向接管，以共同格式交接。
3. Clone 已 Push 的 Repository，加上正確 Vault，在新機重新註冊定位。
4. 本地 Repository 加 Vault，保留 staged、unstaged、untracked 與未 Push 工作。
5. 未正常交接即中斷，從最後保存狀態、Git 與檔案恢復，明示未知。
6. 不同專案重用已驗證技術知識，使用前核對環境、版本與限制。

## 功能需求與驗收追溯

| ID | 必要能力 | 驗收編號 |
| --- | --- | --- |
| FR-01 | 識別 Git Root、Branch、HEAD、Working Tree | 1、4、10、11 |
| FR-02 | 穩定 Project／Vault／Project Memory ID | 3、5、6、16 |
| FR-03 | Git 可提交 Binding，不含機器路徑或憑證 | 3、5、12 |
| FR-04 | 多 Vault Registry、候選與重新定位 | 5、6、7 |
| FR-05 | 先驗證雙向關聯、Schema 與本機授權 | 5、7、16 |
| FR-06 | Agent 無關 State／Handoff 格式 | 1、2、4、11 |
| FR-07 | 恢復時核對實際 Git／檔案與不確定性 | 1、4、10、11 |
| FR-08 | 共用知識、生命週期、適用條件與證據 | 8、10 |
| FR-09 | 精確去重與近似候選，禁止未核准實質合併 | 9 |
| FR-10 | 寫前驗證、衝突、備份及復原 | 7、12、14 |
| FR-11 | Codex／Claude 最小適配及手動降級 | 1、2、13 |
| FR-12 | 保留既有規範、私人設定及工作樹 | 4、12 |
| FR-13 | 有界讀取、低干擾、無背景服務仍可用 | 13、15 |
| FR-14 | 區分搬遷、Fork、副本與分歧 | 6、7、16 |

## 非功能需求

- 核心儲存、解析、搜尋離線可用，不需要模型 API。
- 普通文字編輯器可讀；UTF-8、可攜相對路徑，不硬編碼 Windows 私人目錄。
- 不因錯誤而自動建立空 Vault 或把不可讀當成沒有記憶。
- 恢復命令預設唯讀；不自動 Commit、Push、Checkout、Reset、Clean、Stash。
- 不每訊息掃 Vault，不無意義重寫記憶，不重跑無關測試。
- 不執行不可信筆記指令；限制讀取與輸出範圍。
- 驗證結果有時間、來源與對應程式碼狀態，不把舊通過當成新通過。
- 不擅改 AGENTS.md、CLAUDE.md、REQUIREMENTS.md、AGENTS-MAINTENANCE.md 或 prompts/。

## 記憶分工

建議 v0.1 的 Project State、Handoff、Decisions 以 Repository 為權威；Vault 保存共用知識與反向索引，不重複維護目前進度。ID 不能取代私人記憶授權。

Handoff 至少包含：來源 Agent、時間、任務、完成／未完成事項、主要檔案、Branch／Commit、Working Tree、測試結果、Blockers、下一步、風險及未確認假設。

知識至少視情境包含：ID、分類、標題摘要、來源專案、時間、OS／環境／版本、步驟、驗證與結果、限制、失敗方案、來源關聯及生命週期。狀態為 verified、experimental、deprecated、superseded。

## MVP 與非目標

MVP 必須涵蓋全部 FR，不可將 Binding 當成未來附加功能。

非目標：完整聊天封存、未落盤內容恢復、雲端記憶、向量資料庫、本地模型、強制 QMD／MCP／Hooks、全 Vault 整理、背景服務、自動近似合併、Vault 同步／CRDT、GUI、自動修改全域 Agent 設定。

## 邊界與尚待批准事項

- 只持有 GitHub 程式碼，無法恢復未提交檔案；只持有 Vault，也不等於具備程式碼環境。
- 離線 ahead／behind 以本機 tracking refs 為準，遠端即時狀態可能未知。
- Registry 可避免重複輸入路徑；每次新對話自動觸發仍依賴 Agent 配置。
- 原始碼技術可行性不等於 UAML 已完成驗收。
- 技術與政策提案見 [決策清單](DECISIONS.md)，驗收見 [正式測試](ACCEPTANCE-TESTS.md)。
