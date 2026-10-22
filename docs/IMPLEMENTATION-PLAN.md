# MVP 實作計畫

Phase 4 原計畫，並附 2026-10-22 雛形實作狀態。使用者已授權選取重要項目建立雛形；完整計畫仍不代表所有功能已實作。

## 建議技術

Python 3.11+、Git CLI、PyYAML 作為唯一必要第三方 runtime 依賴；JSON Schema 作為規格／測試契約。Markdown 保存內容，YAML 保存 Manifest/frontmatter，JSON 保存 Registry/checkpoint/索引。實作前固定支援版本及安全解析限制，不使用不安全 yaml.load。

本輪採 Python／PyYAML 建立可逆的雛形，不另引入 Go 或第二套核心。正式發布支援範圍仍待驗收。

## 預計檔案

```text
pyproject.toml
src/uaml/
  cli.py
  schemas.py
  paths.py
  git_state.py
  registry.py
  binding.py
  recovery.py
  project_memory.py
  knowledge.py
  dedup.py
  storage.py
schemas/
templates/
adapters/codex/
adapters/claude-code/
tests/unit/
tests/integration/
tests/security/
tests/acceptance/
```

模組責任見 [架構](ARCHITECTURE.md)。避免一開始引入 web server、資料庫、插件框架或供應商 SDK。

## 命令介面草案

```text
uaml doctor
uaml resolve
uaml recover
uaml validate
uaml vault register <path>
uaml vault relocate <vault-id> <new-path>
uaml vault compare [--knowledge]
uaml vault select <path> --expect-comparison <hash> [--knowledge]
uaml project init --vault <vault-id>
uaml project trust
uaml project fork
uaml checkpoint
uaml knowledge search <query>
uaml knowledge propose <file>
uaml knowledge apply <proposal>
uaml repair
```

目前已實作 doctor、resolve、recover、validate、checkpoint、vault register/relocate/compare/select、project init/trust/fork、vault init、repair 預覽／補完及 knowledge add/get/search/propose/apply。doctor/resolve/recover/validate、vault compare 和 repair 預覽唯讀；repair/fork apply 必須核對 plan_hash。vault select 需 comparison_hash，僅更新本機權威選擇。Knowledge 子樹需明確 read/write grant；propose 僅寫本機提案，apply 才修改 Vault。操作見 [INSTALL](../INSTALL.md)。

## 開發順序

依 [Roadmap](../ROADMAP.MD) 的 M0–M8。先契約、路徑/Git、Binding/Registry，再安全儲存，之後 State/Handoff、知識與適配。安全寫入不能留到最後才補。每個出口依對應測試證據判定，不以檔案數或實作宣告當成完成。

## 測試策略

- 單元：Schema、路徑、身份與錯誤狀態、Unicode／版本去重。
- 整合：臨時 Git Repo、Vault、Registry、多程序寫入、checkpoint 中斷。
- 安全：越界連結、假憑證、惡意筆記、Fork 拒讀、權限不足。
- 平台：Windows 原生 shell／NTFS 必測；其他平台可先 CI，但不可冒稱已正式支援。
- 實機：真實 Codex 新對話、Codex → Claude → Codex、第二台乾淨 Windows 恢復。
- 低干擾：記錄 I/O、載入量、耗時，普通任務不掃描 Vault。

使用隔離合成 fixtures，不以真實 Vault 作破壞性測試。測試失敗修根因，不刪測試或降低需求。同條件已通過時不無目的重跑；變更影響或新證據才擴大驗證。

## 安裝策略

首版建議 Python wheel＋隔離環境，不修改全域 Agent 設定。工具安裝、Vault 註冊、checkout 核准、適配啟用分開。安裝不自動建立 Vault、Git hooks 或背景服務。

卸載工具不刪記憶、Registry 或 Vault；資料清理由使用者另行明確操作。可攜式執行檔留待評估，不先承諾未驗證的封裝能力。

## Windows 實機驗收

記錄 OS/build、Agent 版本、Git、Python、Obsidian、shell、sandbox／權限。覆蓋中文、空白、長路徑、CRLF、junction、ACL、檔案佔用、不同磁碟搬遷、worktree、PowerShell/Git Bash 差異。WSL 測試不得替代原生 Windows。

## 文件與發布清單

實作後補 INSTALL.md、Windows Codex／Claude 使用指南、Binding 操作、跨機遷移、新對話接管、安全隱私、故障排除、授權與發布檢查。只有功能與驗收完成後才發布 v0.1.0；本次 Unreleased 文件提交不是 release/tag。

主要風險與預防見 [安全文件](SECURITY-AND-RISKS.md)，重大選擇見 [待決策事項](DECISIONS.md)。
