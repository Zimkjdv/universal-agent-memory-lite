# 正式驗收計畫

**完整端到端驗收仍未完成。** 2026-10-22 已建立並執行雛形自動測試，覆蓋下表部分程式層案例，但不將其當作全部正式驗收通過。上游 CI 成功不能替代本表。

## 雛形測試範圍

測試命令見 [INSTALL](../INSTALL.md)。tests/test_binding.py 覆蓋 Binding／Fork／搬遷；test_formats.py 覆蓋安全解析及 Windows junction；test_recovery.py 覆蓋保存、過時／未提交內容、中斷與不可信文字；test_git_and_storage.py 覆蓋 CLI、worktree、鎖及備份。讀取拒絕為故障注入，不能冒充完整 Windows ACL 驗收。

T01/T02/T03 的真實 Agent／第二環境尚未執行；Knowledge、去重、完整 repair、ACL 與所有並行案例尚未完成。

### 2026-10-22 本輪驗證記錄

- 執行環境回報 Windows 10 build 19045、Python 3.12.10、Git 2.42.0.windows.2、PyYAML 6.0.3；不是 Windows 11 驗收證據。
- `python -m unittest discover -s tests -t . -v`：46 項通過，沒有 skip；包含實際 Windows junction、活子程序持鎖及 metadata 秘密遮罩案例。
- 本地 editable 安裝成功，`pip check` 無破損依賴；CLI 版本為 0.1.0.dev0。
- `examples/demo.py` 一次性示範通過，包含未授權拒讀、完整恢復及後續變更的 DEGRADED／STALE_MEMORY。
- 文件本地連結與檔名大小寫、code fences、Python 語法已檢查。
- 測試使用臨時資料，未對真實 Obsidian Vault 操作；未宣稱 Windows 11、Codex／Claude 實際接管或第二台電腦已通過。

## 共通證據

記錄案例 ID、時間、OS/build、Agent/Git/UAML 版本、fixtures、前後 hash、CLI JSON、必要對話節錄與判定。使用合成資料／假憑證，不發布私人 Vault。結果為 passed/failed/not_run/unknown；未執行須有原因。

## 16 項核心驗收

| ID | 前置條件 | 操作 | 預期結果與證據 |
| --- | --- | --- | --- |
| T01 New Conversation Recovery | 已核准 Repo、有 checkpoint 及未完成工作 | 保存後結束 Codex 對話，另開新對話啟動恢復 | 找到同一記憶、核對 Git、指出未完成工作；兩段對話與來源 hash |
| T02 Bidirectional Agent Handoff | Codex／Claude 可使用同一 Repo/Vault | Codex → Claude → Codex，各完成一項工作並交接 | 不重講主要背景；三份快照、Git 與驗證結果一致 |
| T03 GitHub + Vault Cross-Machine | Repo／應提交記憶已 Push，正確 Vault 可取得 | 第二個乾淨 Windows 環境 Clone、安裝、註冊、核准、恢復 | 不依賴舊路徑或隱藏設定；新環境記錄、來源 ID 與恢復證據 |
| T04 Local Repository Recovery | staged/unstaged/untracked 及未 Push Commit | 使用本地 Repo＋Vault 恢復 | 正確分類、所有成果 hash 不變；遠端未知不誤報同步 |
| T05 Automatic Binding | 已註冊 Vault、已核准 checkout | 從 Repo 子目錄多次解析 | 定位同一 Vault/memory ID，不反覆問路徑；唯讀無檔案變更 |
| T06 Vault Relocation | 原關聯有效 | 移到其他磁碟／目錄，執行一次 relocate | 只更新本機定位，提交的 IDs 不變，再次恢復成功 |
| T07 Missing or Conflicting Vault | 六類故障 fixtures | 不存在、錯 ID、多候選、記憶缺失、ACL 拒絕、分歧副本逐一測 | 錯誤分類清楚，不建替代 Vault、不寫錯候選；診斷及前後快照 |
| T08 Cross-Project Knowledge | A 保存帶環境及證據的 verified 知識，B 已授權 | B 由另一 Agent 查詢 | 找到同一 ID，使用前核對條件／版本；來源與對話證據 |
| T09 Deduplication | 中英文、相同／近似、不同版本、否定條件資料 | 重複及並行提交 | 相同不新增；近似先提案；差異不誤合併；ID、數量與差異證據 |
| T10 Stale Memory | 舊 Commit、分岔 Branch、不同環境版本 | 恢復及知識查詢 | 實況優先，標示差異；只有記憶更新不誤報功能變更 |
| T11 Crash Recovery | 完整舊 checkpoint，新批次寫入中 | 在各替換階段終止程序 | 偵測不完整、保留可恢復版本，不宣稱復原未保存內容；故障注入記錄 |
| T12 Security & Non-Invasive | 原有規範、假 Token、惡意筆記、越界連結、並行程序 | 讀寫與故障案例 | 不執行注入、不保存假秘密、不擅改規範／全域設定、不刪資料，衝突不覆蓋 |
| T13 Minimal Dependency | 無 MCP/QMD/向量 DB/模型服務/背景程序 | Binding、讀取、checkpoint、恢復；另測人工 Markdown 降級 | 基本 runtime＋Git 即可；記錄環境與結果 |
| T14 Graceful Degradation | 壞 YAML／索引、部分缺檔、未知 Schema | resolve/recover/validate | 明確錯誤與可驗證部分，不靜默清空或自動修復 |
| T15 Efficiency & Low Interference | 大型合成知識集與普通程式碼任務 | 普通對話、一次恢復、一次搜尋 | 普通對話零掃描／重寫，讀取有界、截斷明示，記錄 I/O／耗時／載入量 |
| T16 Rename & Fork | 改名、Remote 變更、保留原 Manifest 的 Fork | 分別解析、確認搬遷或新身份 | 搬遷保留 ID；未核准 Fork 零私人內容讀取；獨立 Fork 新 ID |

## 補充邊界案例

- worktree、detached HEAD、無 HEAD、shallow clone、merge conflict、submodule 邊界。
- 中文／空白／長檔名、大小寫別名、CRLF、junction/symlink 越界。
- Windows ACL、檔案佔用、未知／損壞 Registry。
- 兩 Agent 同時更新知識／Binding／Registry；同時精確去重新增。
- 活程序持鎖超時但未死亡，不得誤刪鎖。
- Obsidian 人工修改後嘗試復原，不得覆蓋新成果。
- 索引遺失可由 Markdown 重建；不完整索引不能認定無重複。
- 任何寫入失敗都不回報完整成功；部分成功逐項說明。

## 不可替代的證據

T01/T02 必須使用真實 Agent 對話；CLI 單元測試不等於接管成功。T03 必須有真正隔離的第二環境，改資料夾名稱不算。Windows 原生實測不能被 WSL 或 Linux CI 取代。

T15 的 32 KiB 摘要與五篇候選是待批准預算；應記錄資料集大小與硬體，不捏造未量測效能。不得為通過而刪案例、放寬需求或隱藏錯誤。
