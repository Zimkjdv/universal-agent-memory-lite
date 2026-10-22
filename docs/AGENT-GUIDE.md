# Codex／Claude 接管指南

目前提供獨立 Markdown 手動入口；自動載入及真實雙向 Agent 對話仍待實機驗收。UAML 不修改既有 AGENTS.md／CLAUDE.md、Agent 全域設定、Hooks 或 MCP。

## 一次性建立入口

在已初始化 UAML 的 Repository，使用已安裝的 uaml CLI：

```powershell
uaml --repo . --json adapter --agent all
# 審閱三份完整 files、actions 與 plan_hash 後套用
uaml --repo . adapter --agent all --apply --expect-plan '<plan-hash>'
```

也可只選 --agent codex 或 claude-code。預覽唯讀、不讀 Vault；套用只建立 .uaml/adapters/WORKFLOW.md 與選定入口 CODEX.md／CLAUDE-CODE.md。hash 綁定目前 Manifest、Git checkout／Remote、目標檔及模板。同內容保留，不同內容拒絕整批套用，不覆蓋自訂檔。中斷時重新預覽，已完成同內容檔保留，剩餘檔建立；多檔建立不宣稱原子交易。

三份文件沒有本機 Vault／Registry 絕對路徑或私人資料，可隨專案提交。安裝入口不授予 checkout／Knowledge 權限；即使 Vault 離線也可產生入口。Registry 使用本機設定，不將路徑寫入專案指令。

## 新 Codex 對話

從正確 Repository 開啟對話，提供：

> 請讀取 .uaml/adapters/CODEX.md，恢復這個專案已持久化的工作。

Codex 依共用流程執行 recover --compact、核對現有規範／Git／實際檔案，回報進度、Blockers、不確定性及下一步。DEGRADED 或截斷須核對診斷與原始來源；未保存內容無法恢復。

Codex 的原生入口由 [官方 AGENTS.md 文件](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 說明。若使用者希望常駐接管提示，可自行在既有專案入口加入條件式短引用：「新對話、Agent 接管或明確保存進度時，讀取 .uaml/adapters/CODEX.md。」這是選配的人工整合，UAML 不自行插入，也不保證桌面版自動載入。

## 新 Claude Code 對話

從相同 Repository 開啟對話，提供：

> 請讀取 .uaml/adapters/CLAUDE-CODE.md，恢復這個專案已持久化的工作。

Claude 使用相同 Manifest／State／Handoff／Registry；保存時 source-agent 為 claude-code。它不把前一個 Agent 的原生記憶當作唯一來源。

[Claude 官方記憶文件](https://code.claude.com/docs/en/memory) 說明 CLAUDE.md、@path 匯入及依版本／設定而異的 AGENTS.md 支援。選配整合可由使用者在現有 CLAUDE.md 人工加入條件式短引用；需要啟動時直接載入且已審核內容時，可自行加入 `@.uaml/adapters/CLAUDE-CODE.md`。這只匯入入口，仍由入口要求讀共用流程。UAML 不自動變更這些檔案或 Claude 設定，不要求複製一套開發規範。

## 交接與異常

在重要里程碑或使用者明確要求時，更新 State／Handoff 的實際內容及驗證結果，再執行 checkpoint --agent codex 或 claude-code；確認 CHECKPOINT_SAVED。切換 Agent 後重新恢復並核對當前檔案，不重用過時測試結果。Git commit／push 是另外的授權動作。

工具不可用時，入口提供人工 Markdown 降級方式；不自動安裝、不建立空 Vault、不自動核准 checkout。缺失／損壞／衝突先回報，原始成果保留。一般訊息無須掃描 Vault 或重寫記憶。

官方資料核對日期：2026-10-22。程式測試只能驗證產生檔案與共用資料契約，不能替代真實 Codex Windows／Claude Code 新對話驗收。
