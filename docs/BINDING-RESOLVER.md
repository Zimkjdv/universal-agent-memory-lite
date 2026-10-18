# Binding Resolver、Registry 與移機

狀態：Phase 3 提案。Resolver 預設唯讀，不建立 Vault、不改 ID、不修改綁定或全域設定。

## Registry 位置與維護

位置優先序：使用者 --registry → 使用者 UAML_HOME → OS 使用者應用資料目錄。Windows 透過 OS API 取得 Local App Data，不硬編碼磁碟或帳號。Repository 不可指定任意本機 Registry 位置。預設位置不可用則報錯，不回退寫入公開 Repository。

以 JSON 保存多 Vault 候選、選定副本、checkout grant。路徑 canonicalize 與去重；不更改 Vault 的邏輯 ID。Registry 更新採鎖、expected hash、暫存替換、上一版備份；備份同樣受限。復原前重新核對路徑與 ID，不自動同步 Registry。

## 身份不等於授權

公開 Manifest 可以被 Fork／複製，不能只憑 UUID 開放私人知識。首次新 checkout 必須確認專案、Vault、memory ID、讀寫子範圍及重要 Binding 指紋。後續新對話可沿用核准，不再輸入路徑。重要身份或 Remote 提示變更須重新檢查。

這是 UAML 工具的政策閘門，不是 OS sandbox；本來有 Vault 檔案權限的其他程序仍可能繞過工具。禁止宣稱能隔離惡意的同使用者程序。

## 介面

```text
resolve(repository_path, registry_path?, mode="read")
  → status
  → project_identity, binding_identity
  → selected_candidate
  → access { read, write, reason }
  → memory_locations
  → diagnostics[]
  → required_action?
```

診斷具穩定機器碼與可理解文字；不可把部分成功扁平化為完整成功。

## 解析順序

1. 用 Git 識別 Root，支援子目錄與 worktree；無工作樹回報。
2. 讀 Manifest，檢查大小、Schema、UUID、路徑、重複鍵。
3. 檢查 checkout grant；未核准不讀私人記憶。
4. 只查 Registry 或使用者明確提供的候選，不掃描全磁碟。
5. 檢查存在性、可讀性、路徑型態、canonical path 及連結邊界。
6. 核對 Vault ID，不依名稱猜測。
7. 多候選未選定時要求選擇；已知分歧不得用 mtime 自動選最新。
8. 核對反向索引的 project_id、vault_id、project_memory_id。
9. 驗證記憶 Schema、缺失與 checkpoint 完整性。
10. 返回能力與位置，由 Recovery 載入必要資料並核對 Git／檔案。

唯讀檢查不建立權限探測檔；寫入能力若無法確認標為未知，在實際明確寫入時驗證。

## 狀態及安全降級

| 狀態 | 行為 |
| --- | --- |
| RESOLVED | 唯一有效、已授權，繼續恢復 |
| BINDING_MISSING | 只提供 Git／Repo 診斷，不初始化 |
| REGISTRY_MISSING / VAULT_UNREGISTERED | 要求一次定位 |
| CHECKOUT_UNTRUSTED | 不讀私人內容，要求確認 |
| VAULT_MISSING | 保留原 ID，提供 relocate 流程 |
| VAULT_ID_MISMATCH | 拒絕候選，不覆寫身份 |
| MULTIPLE_CANDIDATES | 要求選擇，不猜測 |
| REPLICA_CONFLICT | 停止自動寫入，保留差異 |
| READ_DENIED | 不當作空檔或不存在 |
| WRITE_DENIED | 可讀時提供唯讀恢復 |
| PROJECT_LINK_MISSING / MISMATCH | 不借用其他專案記憶 |
| SCHEMA_UNSUPPORTED | 不自動升級／寫回 |
| MEMORY_CORRUPT / CHECKPOINT_MISMATCH | 只使用可驗證資料，明示缺口 |
| WRITE_CONFLICT | 保留提案，拒絕覆蓋 |

Vault 不可用時，Repository 內記憶仍可唯讀使用，但報告明示「共用知識未連接，完整 Binding 未驗證」。不建立替代權威 Vault。

## Rename、移機與 Fork

| 情境 | 規則 |
| --- | --- |
| Repo 改名 | 保留 Project ID，名稱只是顯示 |
| Remote 變更 | 不自動換 ID，確認搬遷／轉移／Fork |
| Repo 新路徑／新 Clone | 保留可攜 ID，核准本機 checkout |
| Vault 改名／移動 | 驗證新路徑 ID，更新 Registry，不改已提交 ID |
| 備份／同步副本 | 保留 Vault ID，列候選並明確選定 |
| 獨立 Fork | 新 Project ID、新 memory ID，不複製私人知識 |
| 同一專案協作用 Fork | 只有明確確認共享關係才保留身份 |

單靠 Git 無法總是區分 Fork 與搬遷。未註冊的副本不在可觀測範圍，不能宣稱找出所有副本。選定候選不等於自動合併內容；分歧需比較並決策。

## 跨機流程

模式 A：取得已 Push Repo 與正確 Vault → 安裝未來 UAML → 註冊新 Vault 路徑 → 核准 checkout → 驗證三個 ID → 恢復 → 核對 Git／檔案。不得依賴舊帳號、磁碟代號或隱藏設定。

模式 B：取得含實際未提交檔案的本地 Repo 與 Vault → 同樣定位及核准 → 分類 staged/unstaged/untracked、未 Push／未知遠端狀態 → 保留成果。GitHub Clone 無法帶回未提交內容。

明確 init／fork／repair 命令才可建立或修復關聯；解析失敗不是自動初始化的授權。
