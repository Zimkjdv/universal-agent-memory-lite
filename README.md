# Universal Agent Memory Lite (UAML)

**Local-first, Markdown-first, portable memory and handoff for AI coding agents.**

UAML 規劃以可攜式 Repository–Vault Binding，連結 Git 專案、專案交接記錄與本地 Obsidian 知識庫，讓 Codex、Claude Code 及未來其他 Agent 接續已持久化的開發工作。

> **目前狀態：研究與設計文件，尚無可安裝的 MVP。**
> Phase 1–4 的研究及規格草案已整理；設計選擇仍待審核。Phase 5 尚未開始，也尚未獲得實作授權。`v0.1.0` 是預計首版，不是已發布版本。

## 目標情境

- 新對話找回專案狀態、未完成工作、Blockers 與下一步。
- Codex → Claude Code → Codex 雙向交接。
- 取得已 Push 的 Repository 與正確 Vault 後，在另一台電腦重新定位及恢復。
- 使用本地 Repository 與 Vault 接續未提交的工作，避免覆蓋使用者成果。
- 跨專案查詢有來源、適用環境與驗證證據的技術知識。
- 異常中斷後使用最後保存資料與 Git 重建必要上下文，明確標示缺失。

UAML 不宣稱恢復未保存的對話、推理、檔案或完整執行環境。

## 建議架構

| 層 | 保存內容 | 權威來源 |
| --- | --- | --- |
| Git Repository | Portable Binding、Project State、Handoff、決策 | 專案開發狀態 |
| Obsidian / Markdown Vault | Vault ID、反向專案索引、技術知識 | 跨專案知識 |
| 本機 Registry | Vault 本機路徑、候選副本、checkout 授權 | 本機定位與允許範圍 |

穩定 ID 不隨資料夾或 Vault 改名而改變。公開 Manifest 不放絕對路徑、憑證或私人設定。ID 只用於識別，**不代表讀取私人 Vault 的授權**。

專案進度以 Repository 為權威；Vault 不維護另一份獨立的「目前進度」。搜尋索引可以重建，不是權威資料。

## 初版原則

- Windows 11 優先，格式與核心介面保留跨平台能力。
- 不綁定模型或 AI 供應商。
- 基本功能不強制依賴 MCP、QMD、向量資料庫、本地模型或背景服務。
- Git、實際檔案與當前驗證優先於歷史摘要。
- 不自動執行筆記指令，不自動合併有實質差異的知識。
- 不擅改既有 `AGENTS.md`、`CLAUDE.md`、需求與安全規範。
- 事件驅動更新，不在每則訊息掃描或重寫 Vault。

Local-first 指 UAML 的儲存、解析與搜尋在本機進行；雲端 Agent 閱讀內容仍受該供應商的資料處理機制影響。

## 文件導覽

| 文件 | 內容 |
| --- | --- |
| [Roadmap](roadmap.md) | Phase 1–7、MVP 順序與批准閘門 |
| [Changelog](CHANGELOG.md) | 真正已完成的變更，與未發布狀態 |
| [產品需求](docs/PRODUCT-REQUIREMENTS.md) | 功能、非功能需求、範圍與非目標 |
| [研究報告](docs/RESEARCH.md) | 固定版本的 Obsidian Mind 原始碼與官方能力研究 |
| [架構](docs/ARCHITECTURE.md) | 權威來源、模組、Git 核對、搜尋與去重 |
| [資料格式](docs/DATA-SCHEMAS.md) | Manifest、Registry、記憶與知識格式草案 |
| [Binding Resolver](docs/BINDING-RESOLVER.md) | 解析流程、授權、移機、Fork 與錯誤狀態 |
| [安全與風險](docs/SECURITY-AND-RISKS.md) | 安全寫入、並行、隱私及保證範圍 |
| [實作計畫](docs/IMPLEMENTATION-PLAN.md) | 建議技術、模組、安裝與驗證方式 |
| [驗收計畫](docs/ACCEPTANCE-TESTS.md) | 16 項正式驗收的條件、步驟及證據 |
| [待決策事項](docs/DECISIONS.md) | 已確認邊界與待批准設計 |

根目錄既有 [REQUIREMENTS.md](REQUIREMENTS.md) 是需求釐清程序，不是 UAML 產品需求；請以 `docs/PRODUCT-REQUIREMENTS.md` 閱讀產品規格。

## 安裝與使用狀態

目前沒有套件、CLI、Hooks、MCP Server 或自動安裝腳本。文件中的命令與資料結構是設計提案，不可當成已可用功能。正式安裝、Codex／Claude 使用、跨機遷移與故障排除指南將隨實作及驗收完成。

「已設定後不用再輸入 Vault 路徑」是 Registry 的目標；「每次新對話完全自動恢復」另依賴 Agent 入口、權限與實機驗證。

## 授權與研究來源

本專案採 [MIT License](LICENSE)。研究參考 Obsidian Mind，但本次僅整理研究與原創設計文件，沒有匯入其程式碼。未來若重用實質程式碼，須保留適用的上游授權通知。
