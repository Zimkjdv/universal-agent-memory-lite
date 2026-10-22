# Changelog

記錄已發生的變更；計畫中的功能請見 [Roadmap](ROADMAP.MD)。日期使用 Asia/Taipei。

## [Unreleased]

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
