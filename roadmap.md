# UAML Roadmap

目標首版：`v0.1.0`。目前為開發前文件階段，沒有已發布版本。

## 階段狀態

| 階段 | 交付 | 狀態 |
| --- | --- | --- |
| Phase 1 — Research & Feasibility | 原始碼研究、Agent 能力、Windows 限制、風險 | 文件完成；實機假設未驗證 |
| Phase 2 — Product Requirements | 正式需求、範圍、非目標、驗收 | 草案完成，待審核 |
| Phase 3 — Architecture & Data Schema | 三層架構、Schema、Registry、Resolver | 草案完成，設計選擇待批准 |
| Phase 4 — Implementation Plan | 開發順序、依賴、安裝、測試計畫 | 草案完成，待審核 |
| Phase 5 — MVP Implementation | 實作核心功能 | **未開始；需使用者明確授權** |
| Phase 6 — Validation & Hardening | 執行驗收、修正缺陷 | 未開始 |
| Phase 7 — Documentation & Release | 安裝／使用指南、發布核對 | 未開始；本次僅建立開發前文件 |

將文件 Commit／Push 不代表批准架構或開始 Phase 5。沒有舊 UAML 版本相容需求。

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

1. 使用者明確批准 Phase 5。
2. [待決策事項](docs/DECISIONS.md) 的重大選擇確定。
3. [驗收計畫](docs/ACCEPTANCE-TESTS.md) 完成，失敗與未知均如實記錄。
4. 安裝、Codex、Claude、Binding、遷移、接管、安全及故障排除指南完成。
5. 不以修改測試要求、隱藏錯誤或使用模擬替代必要實機驗收。
