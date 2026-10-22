# Universal Agent Memory Lite (UAML)

**Local-first, Markdown-first, portable memory and handoff for AI coding agents.**

UAML 以可攜式 Repository–Vault Binding，連結 Git 專案、專案交接記錄與本地 Obsidian 知識庫，讓 Codex、Claude Code 及未來其他 Agent 接續已持久化的開發工作。

> **目前狀態：可本地安裝的 CLI 雛形 `0.1.0.dev0`，完整 MVP 尚未完成。**
> 2026-10-22 已獲授權先實作 Roadmap 的部分核心項目。具備身份初始化、Registry、checkout 授權、保存／恢復與中斷補完，以及明確授權的共用知識儲存／搜尋、去重、安全修訂與雙向替代關聯；已有 Agent 獨立手動入口，真實接管與跨機驗收仍待完成。`v0.1.0` 是目標首版，不是已發布版本。

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
| [Roadmap](ROADMAP.MD) | Phase 1–7、MVP 順序與批准閘門 |
| [Changelog](CHANGELOG.md) | 真正已完成的變更，與未發布狀態 |
| [雛形安裝與試用](INSTALL.md) | 本地安裝、一次性示範、命令與已知限制 |
| [Codex／Claude 接管指南](docs/AGENT-GUIDE.md) | 最小適配入口、手動啟用、新對話及雙向交接 |
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

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe examples/demo.py
```

示範只使用臨時 Repository／Vault。實際試用見 [INSTALL.md](INSTALL.md)。目前可用命令：`vault init/register/relocate/compare/select`、`project init/trust/fork`、`doctor`、`resolve`、`validate`、`checkpoint`、`recover`、`repair`，支援 JSON 與非零錯誤碼。validate 預設唯讀，--knowledge 額外檢查已授權的知識關聯；repair 與 fork 套用需明確提供預覽 plan_hash。完整規格中的其餘命令仍是提案。

trust 預設只授予該專案反向索引讀取；明確使用 `project trust --knowledge read/write` 才開放綁定的 Knowledge 子樹。可用 `knowledge add/search/get` 保存及查詢有來源、適用環境與驗證資訊的 Markdown；不授權 Vault 其他區域。雛形沒有 Hooks、MCP Server 或背景服務，不自動修改既有 Agent 入口。

完全重複會回傳既有 ID；近似內容需審查後明確保留，版本與環境差異不自動合併。修改筆記先使用 `knowledge propose` 檢視差異，再以 `knowledge apply --expect-plan` 套用；若來源、Vault、目標或知識目錄改變，需重新提案。

`knowledge supersede` 明確選擇舊／替代 ID 及原因，審閱後才套用雙向關聯；保留正文、環境與驗證。未完成交易以 Vault 標記阻擋知識使用，原私有計畫可續做，人工修改則拒絕覆蓋。替代不代表跨版本相容或重新驗證，詳見安裝指南。

獨立 Fork 必須明確指定目標 Vault。流程建立新 Project／Memory ID 與空白狀態，舊記憶只在本機封存，不自動讀取來源 Vault、不搬移私人知識、不繼承 checkout 授權。它不修改 Git Remote 或自動 Commit。

已註冊 Vault 副本的本專案索引分歧會阻擋解析；知識內容分歧在明確知識操作時阻擋。以 `vault compare`（知識加 `--knowledge`）審查，再用 `vault select --expect-comparison` 指定權威。內容改變後須重新審查；工具不自動同步、合併或刪除副本，也不在一般恢復時掃描整個 Vault。

「已設定後不用再輸入 Vault 路徑」是 Registry 的目標；「每次新對話完全自動恢復」另依賴 Agent 入口、權限與實機驗證。

`recover --compact` 提供預設最多 32 KiB 的 JSON 接管證據，保留來源與診斷，優先任務／Blockers／下一步，並明示所有截斷。需要完整資料時依來源檔案與 hash 核對；一般 recover 的介面保持原樣。

`adapter --agent all` 預覽 Codex／Claude 的獨立手動入口，`--apply --expect-plan` 才建立檔案；兩者共用一份流程，不修改既有 Agent 規範或全域設定。詳見接管指南；真實 Agent 自動載入與雙向對話驗收仍未完成。

## 授權與研究來源

本專案採 [MIT License](LICENSE)。研究參考 Obsidian Mind，但本次僅整理研究與原創設計文件，沒有匯入其程式碼。未來若重用實質程式碼，須保留適用的上游授權通知。
