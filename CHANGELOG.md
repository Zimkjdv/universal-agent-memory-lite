# Changelog

記錄已發生的變更；計畫中的功能請見 [Roadmap](ROADMAP.MD)。日期使用 Asia/Taipei。

## [Unreleased]

### Fixed — 2026-10-29：跨平台 Clone 驗證

- CI 發現遷移 fixture 的一次性 -c core.autocrlf 設定沒有保留到目的地，Linux 隨後正確偵測到 dirty worktree。
- 改用 clone --config 持久設定並驗證目的地值；新增目的地設定改變後仍須要求審查的回歸案例，保留原 byte／hash 驗收要求。

### Added — 2026-10-29：第四輪優先項目 3

- 明確的 sdist 文件／測試／示範 manifest、SPDX MIT／license-files、project URLs 與可選 dev 建置依賴。
- verify_distribution.py：artifact 路徑／inventory／metadata／license／entry point 檢查，在獨立 venv 離線安裝、驗證來源並執行示範及完整測試。
- Windows／Ubuntu × Python 3.11／3.12 CI，官方 Actions 固定 SHA、唯讀內容權限，不持久保存 checkout 憑證。
- 5 個 artifact 防護／依賴比較案例及發布前檢查表；未建立 release、tag 或 PyPI 上傳。

### Added — 2026-10-29：第四輪優先項目 2

- migration check --mode github/local：唯讀檢查來源身份、checkpoint／章節、Git 保存差異、byte-exact HEAD、local tracking evidence、待完成 journal 及疑似已追蹤的私有 artifacts。
- --knowledge 只使用明確既有 grant；缺失／未完成／損壞／超限明示，不自動授權或建立替代 Vault。
- migration rules 預覽／hash 確認套用四檔的 -text 規則，保留既有 .gitattributes、index、全域設定；檢查 filter／encoding override。
- 新機定位與遷移指南；本地 bare remote 的 CRLF Clone／新 Registry／不同 Vault 路徑及 staged／unstaged／untracked 複製驗證。

### Added — 2026-10-29：第四輪優先項目 1

- registry audit：不依賴 Git 的本機 Registry／已知私有 artifacts 權限稽核，最多 1024 項。
- Windows 原生 owner／DACL／ACE 讀取與保守授權分類；Unix owner／mode／extended ACL 未確認診斷。
- 權限不足、未知 ACE、null／empty DACL、連結、多 hard links、巢狀或超限不誤報安全。
- 不讀正文、不改 ACL／設定、不建立 Registry；新增 10 案例，含真實 Windows Everyone grant fixture。

### Added — 2026-10-22：第三輪優先項目 3

- knowledge supersede 預覽、私有 before/after 計畫、完整 payload 路徑與明確 hash 套用。
- 雙向 supersedes／superseded_by、supersession_reason、revision／來源追蹤；保留正文、環境、證據與歷史鏈，不自動合併。
- Repo／Vault 鎖、完整目錄與 payload 檢查、備份、pending 標記、中斷續做及完成後冪等；人工修改拒絕覆蓋。
- get/search/validate --knowledge 拒絕未完成狀態，讀取前後收據檢查防止交易完成期間的混合結果。
- 單篇提案不可修改替代原因／關聯或復活 superseded 筆記。

### Added — 2026-10-22：第三輪優先項目 2

- adapter --agent codex/claude-code/all 預覽完整檔案；--apply --expect-plan 才建立獨立 Markdown 手動入口。
- 一份 WORKFLOW 共用恢復、核對、降級及事件驅動保存流程，Agent 入口只指定名稱與觸發條件。
- 目標／身份／模板 hash 與合作鎖防護，不同內容整批拒絕、相同檔保留；不修改既有規範、全域設定或權限。
- Codex／Claude 新對話指南、人工選配引用與實機驗收邊界。

### Added — 2026-10-22：第三輪優先項目 1

- recover --compact：預設 32 KiB、可調 8–64 KiB 的 UTF-8 JSON 輸出上限，包含排版與換行。
- 以來源 hash／完整性／Git 差異為基礎，優先保留任務、Blockers、下一步及風險，讀到長筆記末尾章節。
- 省略數量與章節截斷明示；不推論事實、不讀知識、不修改資料，保留既有完整 recover 介面。
- 10 個新增案例覆蓋實際 CLI bytes、Unicode／跳脫、缺失／過時、唯讀與完整介面相容性。

### Added — 2026-10-22：第二輪優先項目 3

- vault compare/select：已註冊副本的有界唯讀比較、機器可讀 hash、衝突及明確權威選擇。
- Resolver 比對已授權身份及本專案索引；知識操作額外比對授權 Knowledge，不在普通恢復時掃描知識。
- 本機 replica_resolutions 綁定專案、候選及比較 hash；內容改變使舊確認失效，register --select 不能略過分歧。
- 缺失舊路徑明示，不可讀／錯身份／損壞候選拒絕確認；不自動合併、同步、刪除或建立替代 Vault。
- 14 個新案例覆蓋比較、CLI、授權、過期確認、知識分歧及不變更原資料。

### Added — 2026-10-22：第二輪優先項目 2

- project fork 明確目標 Vault、私有計畫／原檔封存、hash 綁定預覽與套用。
- 新 Project／Memory ID、空白交接與反向索引，不讀取來源 Vault 或繼承私人知識／grant。
- 僅替換四個 UAML 管理檔；原程式碼與 Git index 保留；人工變更／Remote 變更／payload 竄改拒絕。
- Manifest 最後切換、中斷續做及完成後冪等；trust 與身份變更使用同一 Repo 合作鎖。

### Added — 2026-10-22：第二輪優先項目 1

- 唯讀 validate 與可選 --knowledge，集中回報綁定、記憶、checkpoint 與 Git 差異。
- 必填章節的非空／唯一檢查，排除程式碼區塊的假標題。
- 已授權的知識缺失引用、supersession 正反關係與循環檢查。
- 11 個驗證案例，保留部分可讀資料、不執行筆記、不修改或修復內容。

### Added — 2026-10-22：優先項目 3

- 新增時精確去重；相同環境的 Unicode/CJK 近似候選僅提議，需 review_hash 與明確保留旗標。
- 版本、OS、架構、前置條件先分組，保留否定詞，不自動合併不同條件記錄。
- knowledge propose/apply：本機提案、差異、payload hash、原檔 hash、整份目錄 hash、checkout／Vault 核對與原內容備份。
- 修訂必須保留來源／建立時間並遞增 revision；步驟或環境變更不能沿用 verified 舊驗證時間。
- 中文／否定／版本、雙程序重複新增、提案過時／竄改、手動修改與 CLI 測試。

### Added — 2026-10-22：優先項目 2

- knowledge add/get/search、單層有界 Unicode 檢索、環境與精確版本篩選。
- project trust --knowledge none/read/write，舊 grant 預設沒有知識權限。
- Knowledge Schema、verified 證據要求、來源／適用條件／hash 輸出與合成範本。
- 跨專案授權、唯讀搜尋、損壞與超限降級、秘密拒絕及 CLI 案例測試。

### Added — 2026-10-22：優先項目 1

- checkpoint journal v2 在寫入前保存可驗證 before/after payload。
- repair 唯讀預覽與明確套用；綁定 plan_hash、Project／checkout 身份與每個目標 hash，checkpoint 最後公布。
- 人工編輯、損壞 payload、遺留鎖與舊 journal 安全拒絕；已完成交易不得覆蓋後續內容。
- 復原、CLI 與拒絕案例測試；此項獨立 Commit／Push 後才開始下一項。

### Added — 2026-10-22

- Python CLI 雛形 `0.1.0.dev0`、本地隔離安裝方式與一次性示範。
- 嚴格 YAML／JSON 解析、UUID 與標準記憶路徑驗證、連結越界防護。
- Vault／Project 初始化、Registry 註冊與重新定位、候選選擇及 checkout 授權。
- 唯讀 Binding Resolver、Git 觀察與 State／Handoff 恢復，支援 JSON 與錯誤碼。
- 手動編輯 Markdown 後 checkpoint：更新快照、hash、備份、交易紀錄與中斷偵測。
- 隔離自動測試，涵蓋未授權 Fork、搬遷、未提交變更、過時內容、Windows junction、鎖與中斷。

### Changed — 2026-10-22

- `roadmap.md` 改名為 `ROADMAP.MD`，同步更新文件引用。
- 記錄使用者對部分 Phase 5 雛形的授權與實際範圍。
- 完整 MVP、共用知識、Agent 整合、自動修復與跨機驗收維持未完成。

### Added — 2026-10-18

- 建立 UAML 專案介紹及文件導覽。
- 保存 Phase 1–4 的研究、產品需求、架構與資料格式草案。
- 記錄 Repository–Vault Binding、Registry、checkout 授權與 Resolver 設計。
- 記錄安全更新、去重、過時記憶與異常中斷處理方案。
- 建立分階段實作計畫、16 項驗收規格及待批准決策清單。
- 研究引用固定 Obsidian Mind Commit，區分靜態分析、上游 CI 與未執行的實機驗證。

### Status

- `v0.1.0` 僅為目標版本，尚未發布。
- 已有 CLI、Registry、Resolver 與基本保存／恢復雛形；Agent 整合尚未完成。
- 已執行雛形自動測試；16 項正式端到端驗收尚未全部執行。
- Phase 5 的部分雛形已於 2026-10-22 獲授權；不是正式發布。
