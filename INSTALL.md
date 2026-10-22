# 雛形安裝與操作

目前是 `0.1.0.dev0` 開發雛形，尚未發布 v0.1.0。只在隔離／測試資料上試用；完整 MVP 與真實跨 Agent／跨機驗收仍未完成。

## Windows 本地安裝

需要 Python 3.11+ 與 Git。PowerShell 在本專案根目錄執行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uaml --help
```

只安裝到專案 .venv；runtime 第三方依賴為 PyYAML，建置使用 setuptools。不需要啟用 PowerShell activate 腳本、不修改全域 Agent 設定。Unix 類環境使用 `.venv/bin/python`，目前正式實測以 Windows 為主。

## 一次性示範

```powershell
.\.venv\Scripts\python.exe examples/demo.py
```

程式在系統暫存目錄建立 Repo、Vault、Registry，執行初始化、未授權拒讀、核准、保存、恢復及過時偵測，結束時清理自己的暫存資料。使用實際安裝的 CLI，不觸碰既有 Vault。

## 手動試用流程

先準備測試用 Git Repository 與已存在的空 Vault 資料夾。以下路徑是需自行替換的範例；Registry 放在 Repository 與 Vault 之外。

```powershell
$repoPath = 'D:\Test\my-project'
$vaultPath = 'D:\Test\my-vault'
$registryPath = 'D:\Test\private\registry.json'
$pythonPath = '.\.venv\Scripts\python.exe'

& $pythonPath --registry $registryPath --json vault init $vaultPath --name 'Test Vault'
& $pythonPath --registry $registryPath --json vault register $vaultPath
# 將下列值替換為前一步的 vault_id
& $pythonPath --repo $repoPath --registry $registryPath --json project init --vault '<vault-id>' --name 'Test Project'
# 先檢視 Repository 的 .uaml/project.yaml 與 Vault 反向索引
& $pythonPath --repo $repoPath --registry $registryPath project trust
& $pythonPath --repo $repoPath --registry $registryPath resolve
```

`vault init` 只為明確提供且已存在的目錄建立身份；不註冊、不建立替代 Vault。`register` 不初始化缺失身份。`project init` 建立 Binding、反向索引、兩份 Markdown 與第一個 checkpoint；遇到既有檔案拒絕覆蓋。它不更動 AGENTS.md／CLAUDE.md，也不自動授權新 checkout。

## 保存與恢復

手動或由 Agent 編輯 `docs/memory/PROJECT-STATE.md` 和 `HANDOFF.md` 的正文，補齊任務、下一步、驗證及風險；保留有效 frontmatter。然後：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath checkpoint --agent codex
& $pythonPath --repo $repoPath --registry $registryPath recover
& $pythonPath --repo $repoPath --registry $registryPath --json recover
```

checkpoint 保留正文，更新時間／Agent／Git 快照、revision、snapshot_id 及完整性 hash。這只表示資料已保存，不表示正文經技術驗證。它是明確 Repo 寫入操作，不授予 Vault 存取。

recover／resolve／doctor 為唯讀，不更新 Registry 或索引。recover 輸出歷史資料、來源 hash、完整性及 Git 差異；不執行筆記內容。Vault 不可用時仍嘗試讀 Repo 記憶並回報 DEGRADED。

## 共用技術知識

預設 trust 只允許反向專案索引，不會自動取得知識權限。要試用時明確選擇：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath project trust --knowledge write
# 其他專案只需要查詢時用 --knowledge read；none 可撤銷
```

範圍只限已綁定 Vault 的 layout.knowledge，不授權整個 Vault。write 包含 read；重新執行不帶 --knowledge 的 trust 會重設為 none。

複製 [知識範本](examples/knowledge-template.md)，替換 UUID、source_project_ids（目前 .uaml/project.yaml 的 project.id）、時間、環境與內容，然後：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath knowledge add 'D:\Test\my-note.md'
& $pythonPath --repo $repoPath --registry $registryPath knowledge search 'Python 安裝' --os windows --component python --component-version 3.12
& $pythonPath --repo $repoPath --registry $registryPath knowledge get '<knowledge-id>'
```

add 只建立 revision 1 的新 ID，拒絕覆蓋及沒有目前來源專案的匯入。verified 必須有 OS、架構、元件版本、checked_at 和 method/result 證據；UAML 驗證資料完整性，不假裝替使用者重跑實際技術測試。跨專案查詢顯示來源、狀態、適用環境、驗證與 hash，使用前仍須核對。

預設排除 deprecated/superseded；可用 --status 明確查詢。版本篩選為字串精確比對，不推斷版本區間相容性。預設最多 5 筆、每筆正文 2 KiB；get 最多正文 12 KiB，截斷明示。每次明確搜尋掃描單層 Knowledge，最多 200 個目錄項與 16 MiB 有效筆記；壞筆記、巢狀／連結或超限回報 DEGRADED，不宣稱完整。沒有背景索引或每訊息掃描。

此階段的語意去重與安全修訂在下一優先項目處理；沒有自動合併或修改關聯筆記。

## 搬遷與候選副本

```powershell
& $pythonPath --registry $registryPath vault relocate '<vault-id>' 'E:\MovedVault'
```

ID 必須相同，不改 Repo Manifest。保留舊候選紀錄並明確選定新位置。多份同 ID 副本註冊後會取消隱含選擇；`vault register <path> --select` 代表明確選擇，不代表內容已合併或所有副本已比對。若 Vault 身份檔／layout 變更，需重新 trust。

## 輸出與故障

- 全域參數 `--repo`、`--registry`、`--json` 放在子命令之前。
- 完整成功 exit 0；DEGRADED、衝突、損壞、未授權等 exit 1；命令用法錯誤 exit 2。
- Registry 順序：--registry → UAML_HOME/registry.json → OS 使用者資料目錄。唯讀命令不自動建立它。
- 若 Git 報 dubious ownership，先確認檔案擁有者；請以 Repository 擁有者帳號執行，或自行審核 Git 信任設定。工具不修改 safe.directory，也刻意不接受環境內 GIT_DIR/GIT_CONFIG_* 覆寫，避免解析錯 Repo。
- 遺留 `.uaml/write.lock` 或 Registry `.lock`：先確認沒有活程序，不自動刪除或按鎖齡搶鎖。
- 半完成 checkpoint：停止重存，使用下列預覽／套用流程；不要盲目刪除 checkpoint 或搶鎖。
- 雛形只接受標準三個 docs/memory 路徑；自訂路徑尚未開放。
- 讀寫限本機合作程序。Windows ACL 保護依目前使用者目錄繼承，完整權限強化與非合作編輯競態仍待驗收。

## 中斷 checkpoint 的安全復原

從 Registry 同層 `transactions/<snapshot-id>.json` 找出 prepared 交易。新交易會先保存完整 before/after payload，再開始替換 Repo 記憶。repair 只能補完這個已保存快照，不生成新內容：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json repair --transaction '<snapshot-id>'
# 檢視 actions 後，複製輸出的 plan_hash
& $pythonPath --repo $repoPath --registry $registryPath --json repair --transaction '<snapshot-id>' --apply --expect-plan '<plan-hash>'
```

預覽完全唯讀；apply 在合作鎖內重新檢查身份、payload 及每個目標 hash，最後公布 checkpoint。任一目標已被另外修改、Binding 改變或 payload 損壞，全部檢查通過前不寫入。apply 中再中斷可重新預覽後續步驟。只保留及補完資料，不刪除或回滾人工成果。

舊 schema_version 1 journal 沒有可驗證 payload，回報 REPAIR_UNSUPPORTED，需人工核對備份；不假造 after-image。真實程序被終止後可能遺留 lock，工具不按時間自動移除，需使用者先確認持有者。Vault 反向索引初始化若在 journal 建立之前中斷，不在此 repair 的涵蓋範圍。

## 開發驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

使用標準函式庫 unittest，測試建立臨時 Repo／Vault；沒有 pytest、MCP、QMD 或背景服務依賴。正式十六項驗收的進度與尚未驗證部分見 [驗收計畫](docs/ACCEPTANCE-TESTS.md)。
