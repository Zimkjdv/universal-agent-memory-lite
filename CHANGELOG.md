# Changelog

記錄已發生的變更；計畫中的功能請見 [Roadmap](ROADMAP.MD)。日期使用 Asia/Taipei。

## [Unreleased]

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
