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

### 去重與刻意保留近似內容

add 會在同一把 Vault 鎖內重新掃描及去重。完全相同內容及適用條件回傳 KNOWLEDGE_DUPLICATE 與既有 ID，不建立另一份權威；不同來源或再次驗證日期不自動合併到舊筆記，要保留這些資訊時請修訂既有 ID。

近似內容回傳 KNOWLEDGE_SIMILAR、候選與 review_hash，exit 1，不寫入。若差異確實有意保留，檢視後明確執行：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json knowledge add 'D:\Test\my-note.md'
& $pythonPath --repo $repoPath --registry $registryPath knowledge add 'D:\Test\my-note.md' --allow-similar --expect-candidates '<review-hash>'
```

review_hash 綁定輸入內容及目前知識目錄，變更後須重新審查。純文字 Unicode/CJK 候選不宣稱理解所有語意；不移除否定詞。元件版本、OS、架構及 conditions 不同時保留不同記錄，不自動合併。損壞筆記或掃描超限時拒絕新增／提案／套用，不用不完整搜尋來宣稱沒有重複。

### 安全修訂

取出現有筆記並保留 id／created_at／所有原來源專案，revision 加一、updated_at 不倒退；加入當前修改專案來源，編輯後：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json knowledge propose 'D:\Test\revised-note.md'
# 檢視 untrusted_diff、候選及完整 payload 後再套用
& $pythonPath --repo $repoPath --registry $registryPath knowledge apply '<proposal-id>' --expect-plan '<plan-hash>'
```

propose 只在 Registry 同層 proposals/ 保存本機提案／payload，不寫 Vault；read grant 可提案，apply 必須 write grant。差異超過 12 KiB 時明示截斷並附完整 payload 位置，不能把截斷摘要當成完整審閱。提案綁定 checkout、Project／Vault、原檔、payload 與整份目錄 hash；任何改變都拒絕套用。成功修改會備份原檔；不刪除或合併其他筆記。

若有近似候選，apply 額外需要明確 --allow-similar。完全重複仍不得透過此參數建立第二份權威。修改 verified 的步驟或適用條件時，需更新較新的 checked_at 與有效證據，或明確降為 experimental；UAML 不代為執行驗證命令。可帶原因 deprecated 單篇筆記；跨筆記 supersedes/superseded_by 交易尚未支援，拒絕用單篇修訂改寫。

## 搬遷與候選副本

```powershell
& $pythonPath --registry $registryPath vault relocate '<vault-id>' 'E:\MovedVault'
```

ID 必須相同，不改 Repo Manifest。保留舊候選紀錄並明確選定新位置。多份同 ID 副本註冊後會取消隱含選擇；`vault register <path> --select` 或 relocate 只指定初步位置，不能略過已知內容分歧。若 Vault 身份檔／layout 變更，需重新 trust。

### 比較並選定副本權威

先指定可用且具有本專案反向索引的候選，核准 checkout，再比較：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json vault compare
# 審查各副本的身份、索引 hash、缺失與錯誤；複製 comparison_hash
& $pythonPath --repo $repoPath --registry $registryPath vault select $vaultPath --expect-comparison '<comparison-hash>'
# 額外比對 Knowledge 需已有 read/write grant；比較與選擇都加 --knowledge
& $pythonPath --repo $repoPath --registry $registryPath --json vault compare --knowledge
& $pythonPath --repo $repoPath --registry $registryPath vault select $vaultPath --knowledge --expect-comparison '<knowledge-comparison-hash>'
```

compare 唯讀，僅列 hash 與診斷，不把筆記當指令。一般 resolve/recover 只比對已註冊副本的身份檔與本專案 PROJECT.md；知識操作及明確 --knowledge 才掃描授權的 Knowledge 子樹。最多比較 8 份候選；每份知識沿用 200 目錄項／16 MiB 限制，不掃描私人其他區域或全磁碟。

REPLICA_CONFLICT 表示目前可用副本內容不同；select 需精確 comparison_hash，僅將本次本專案權威確認寫入本機 Registry。它不合併、同步、刪除或改寫 Vault；單純 register --select 無法確認分歧。確認只適用於當前候選集合與內容 hash；任何後續內容變更（包括合法新增筆記）若造成分歧，就需重新比較及選擇。只比較專案索引的確認不涵蓋知識分歧。

缺失的舊搬遷路徑列為 MISSING，不建立替代內容，也不證明離線副本等價；其餘可用副本仍能解析。錯 ID、不同身份／layout、不可讀、損壞或不完整掃描回報 REPLICA_UNVERIFIED，不能透過 select 忽略。先修正路徑／權限／資料；無有效索引的副本不能選為權威。未註冊副本與候選外變更不在檢查範圍。REPLICA_EQUIVALENT 只表示本次範圍內的可用內容等價，需一併檢視 missing_count。

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

## 唯讀完整性檢查

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json validate
& $pythonPath --repo $repoPath --registry $registryPath --json validate --knowledge
```

檢查綁定、State／Handoff frontmatter、必填非空且唯一的章節、checkpoint hash／snapshot，以及與當前 Git 的差異。程式碼區塊中的標題不會滿足章節要求。缺失或損壞時仍列出其他可檢查項目，不自動修復或寫回。

--knowledge 必須有 read/write grant，否則回報拒絕，不擴權。檢查範圍限 Knowledge 子樹與本專案反向索引，檢查引用、supersession 正反關係及循環。掃描不完整時不宣稱關聯有效。VALIDATED exit 0；VALIDATION_ISSUES exit 1。有效格式不是對歷史敘述或技術解法正確性的認證。

## 開發驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

使用標準函式庫 unittest，測試建立臨時 Repo／Vault；沒有 pytest、MCP、QMD 或背景服務依賴。正式十六項驗收的進度與尚未驗證部分見 [驗收計畫](docs/ACCEPTANCE-TESTS.md)。

## 獨立 Fork 身份

先取得 Fork 的本地 Repository，註冊明確選定的目標 Vault。工具不推斷同一 ID 是否代表合作 Fork 或獨立專案；獨立流程才使用此命令：

```powershell
& $pythonPath --repo $repoPath --registry $registryPath --json project fork --name 'Independent Project' --vault '<target-vault-id>'
# 審閱新 IDs、actions 與 plan_hash；計畫在本機 forks/ 保存
& $pythonPath --repo $repoPath --registry $registryPath --json project fork --proposal '<fork-id>'
& $pythonPath --repo $repoPath --registry $registryPath --json project fork --proposal '<fork-id>' --apply --expect-plan '<plan-hash>'
# 確認新 .uaml/project.yaml 與新反向索引後，再核准新身份
& $pythonPath --repo $repoPath --registry $registryPath project trust
```

預覽不修改 Repo／Vault，只在 Registry 同層 forks/ 保存原四檔與新 payload。apply 明確替換 PROJECT-STATE.md、HANDOFF.md、checkpoint.json 與 .uaml/project.yaml，原內容保留本機封存及備份；新狀態是空白模板，不把舊進度當新事實。Git 程式碼、staged／unstaged 成果與 Agent 規範不變，來源 Repo／Vault 反向索引不修改。目標 Vault 必須明確提供，甚至來源 Vault 離線也能為另一個目標建立獨立身份。

apply 先檢查全部身份／payload／目前 hash，在 Repo＋Vault 合作鎖內撤銷本 checkout 舊 grant，建立空白新反向索引，再替換記憶，Manifest 最後切換。中斷後可用同一 proposal 再預覽／套用；只接受精確 before 或 after，人工修改後拒絕覆蓋。完成後重複 apply 是 no-op，不撤銷後來核准的新 grant。

Fork 不會設定新 Remote、不會自動取得 Knowledge 權限或複製私人知識；若為同專案協作用 Fork，應保留身份並另行明確 trust，而非執行獨立流程。跨檔／跨位置操作不宣稱分散式原子交易；遺留活鎖不得自動搶走。
