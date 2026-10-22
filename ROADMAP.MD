# UAML Roadmap

目標首版：`v0.1.0`。目前為 CLI 雛形 `0.1.0.dev0`，沒有已發布版本。

## 階段狀態

| 階段 | 交付 | 狀態 |
| --- | --- | --- |
| Phase 1 — Research & Feasibility | 原始碼研究、Agent 能力、Windows 限制、風險 | 文件完成；實機假設未驗證 |
| Phase 2 — Product Requirements | 正式需求、範圍、非目標、驗收 | 草案完成，待審核 |
| Phase 3 — Architecture & Data Schema | 三層架構、Schema、Registry、Resolver | 草案完成，設計選擇待批准 |
| Phase 4 — Implementation Plan | 開發順序、依賴、安裝、測試計畫 | 草案完成，待審核 |
| Phase 5 — MVP Implementation | 實作核心功能 | **2026-10-22 已授權部分核心雛形；實作中** |
| Phase 6 — Validation & Hardening | 執行驗收、修正缺陷 | 已有雛形自動測試；完整 16 項驗收未完成 |
| Phase 7 — Documentation & Release | 安裝／使用指南、發布核對 | 已有雛形安裝指南；正式使用指南／發布未完成 |

2026-10-18 的文件 Commit／Push 不構成開發批准；2026-10-22 使用者另行授權依 Roadmap 挑選重要項目建立雛形，並授權完成後 Commit／Push。此授權不表示完整 MVP 或待選功能全部獲准。沒有舊 UAML 版本相容需求。

## 本輪實作範圍（2026-10-22）

- M1：安全 YAML／JSON、標準路徑、Git Root／worktree／狀態與內容差異觀察。
- M2：Vault／Project 初始化、Registry、候選副本、重新定位、checkout trust、唯讀 Resolver。
- M3 子集：合作鎖、expected hash、備份、checkpoint 最後公布、半完成偵測；自動 repair、ACL 強化及所有並行邊界仍未完成。
- M4 子集：State／Handoff 模板、手動編輯後保存、唯讀恢復、來源與過時診斷。
- 可執行的一次性示範與隔離測試。M0–M4 均不因有子集實作就整體標為完成。
- 本輪 46 項自動測試通過；執行環境回報 Windows 10 build 19045，Windows 11 與真實 Agent 驗收仍待完成。證據範圍見 [驗收計畫](docs/ACCEPTANCE-TESTS.md)。
- M5–M8 保持後續工作；未執行真實 Codex／Claude 接管或第二台 Windows 驗收。

## 後續三項優先工作（2026-10-22）

依使用者要求逐項完成、驗證、Commit、Push，推送成功才進入下一項：

1. **M3：中斷 checkpoint 安全復原** — 已完成此子項，57 項測試通過並提交／推送 `20df720`。
2. **M5：共用知識儲存與搜尋** — 已實作明確 read/write grant、嚴格格式、add/get 與有界 Unicode 搜尋；驗證後獨立提交。
3. **M5：知識去重與安全修訂** — 尚未開始。

第一項不包含 stale-lock 強制接管、ACL 強化、任意 rollback 或跨機同步交易；不把 M3 整體標為完成。

## Phase 5 建議里程碑

| 里程碑 | 工作 | 出口條件 |
| --- | --- | --- |
| M0 | 固定規格、Schema、威脅模型與 fixtures | 待決策事項已處理 |
| M1 | 安全路徑、Git 觀察、Schema 解析 | 中文路徑、worktree、惡意路徑、無 HEAD 案例通過 |
| M2 | Registry、Binding、checkout grant | 搬遷、多候選、錯 ID、Fork 拒讀通過 |
| M3 | 安全儲存與 checkpoint | 並行、中斷、替換失敗、復原通過 |
| M4 | State、Handoff、Recovery | 恢復輸出完整，過時狀態明確 |
| M5 | 知識、搜尋與去重 | 跨專案、中文、版本差異與索引失效通過 |
| M6 | Codex／Claude 適配 | 真實雙向接管且不破壞既有規範 |
| M7 | Windows／跨機強化 | 16 項驗收有完整證據 |
| M8 | 發布準備 | 套件、文件、授權與版本核對完成 |

實際工作跨越 Phase 5–7；M7、M8 不能僅靠實作完成而勾選。

## 首版必要成果

- Project–Vault Portable Binding、Registry、Resolver。
- Project State、Agent Handoff、Git 實況核對。
- 共用知識、文字搜尋、基本去重及有效性檢查。
- 安全更新、衝突處理、搬遷與錯誤降級。
- Codex／Claude 最小適配，不強制 Hooks 或 MCP。

## 後續可選方向

MCP、QMD、語意搜尋、Hooks、自訂 Obsidian UI、其他 Agent 與其他 OS。這些不是首版完成的必要條件，也不是目前已核准的工作。

不規劃以分散式鎖、CRDT、背景整理或全聊天封存擴大首版。

## 發布閘門

1. Phase 5 本輪範圍已獲授權；新增重大範圍另依使用者要求確認。
2. [待決策事項](docs/DECISIONS.md) 的重大選擇確定。
3. [驗收計畫](docs/ACCEPTANCE-TESTS.md) 完成，失敗與未知均如實記錄。
4. 安裝、Codex、Claude、Binding、遷移、接管、安全及故障排除指南完成。
5. 不以修改測試要求、隱藏錯誤或使用模擬替代必要實機驗收。
