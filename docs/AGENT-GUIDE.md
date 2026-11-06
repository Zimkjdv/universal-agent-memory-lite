# Codex／Claude 接管指南

目前提供獨立 Markdown 手動入口，以及需要明確審閱／套用的原生短引用。預設不修改 AGENTS.md／CLAUDE.md；--native 只在明確 hash 核准後追加引用，保留原文並備份。原生載入及真實雙向 Agent 對話仍待實機驗收，不變更 Agent 全域設定、Hooks 或 MCP。

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

Codex 的原生入口由 [官方 AGENTS.md 文件](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 說明。它有 override 優先級及合併後的大小預算；產生引用不代表桌面版已實測載入。可使用下方 --native 流程或自行加入條件式短引用。

## 新 Claude Code 對話

從相同 Repository 開啟對話，提供：

> 請讀取 .uaml/adapters/CLAUDE-CODE.md，恢復這個專案已持久化的工作。

Claude 使用相同 Manifest／State／Handoff／Registry；保存時 source-agent 為 claude-code。它不把前一個 Agent 的原生記憶當作唯一來源。

[Claude 官方記憶文件](https://code.claude.com/docs/en/memory) 說明 CLAUDE.md、@path 匯入及依版本／設定而異的 AGENTS.md 支援。新增 CLAUDE.md 可能停止直接載入 AGENTS.md；因此工具新建 CLAUDE.md 且有 AGENTS.md 時，會明示加入 @AGENTS.md 匯入，讓既有規範保留單一來源。已有 CLAUDE.md 保留原文，只追加 Claude 的條件式引用，不代改既有匯入或設定。引用入口後仍需依觸發條件讀共用流程。

## 選配：原生入口短引用

先完成前述手動入口安裝，再執行唯讀預覽：

```powershell
uaml --repo . --json adapter --agent all --native
# 審閱 actions、files 中每段追加內容、dependencies、backup_directory 及 plan_hash
uaml --repo . --json adapter --agent all --native --apply --expect-plan '<plan-hash>'
```

--agent codex 對應 Git root 的 AGENTS.md，claude-code 對應 CLAUDE.md；all 同時預覽兩者。files 只顯示追加文字，完整原檔以 before_hash 綁定，不把既有規範正文重新印出。新建 CLAUDE.md 對原有／同批新建 AGENTS.md 的匯入也列在追加內容內。每個引用有 Agent 名稱及 UAML 標記，觸發新對話、接管中斷工作、明確保存里程碑或交接；不在一般訊息啟動掃描。

原生預覽不寫入、不讀 Vault，要求已安裝且內容匹配的共用入口。計畫綁定 Manifest、checkout／Remote、原生檔、共用檔原始 hash、匯入依賴及私人備份位置。原生檔保留所有原始 bytes，追加時沿用一致 CRLF；UTF-8 BOM 保留。32 KiB 是單檔上限，Agent 合併後的上下文預算仍需另行核對。

套用先在 Registry 同層 adapter-backups/ 保存每份既有原文，再核對完整計畫、逐檔以 expected hash 公布。備份子目錄新建時受限；既有備份目錄權限若無法確認則停止，不自動改 ACL。備份列入 registry audit，JSON 結果的 backups 提供原文位置；請勿把含私有內容的備份或輸出提交公開 Git。原生引用本身只有可攜式相對路徑。

相同引用再次套用不重複追加。自訂／不完整／重複／藏在 code fence 的 UAML 標記、未閉合 fence/comment、硬連結／符號連結、疑似憑證或檔案變動會拒絕自動處理。存在 AGENTS.override.md 時 Codex 自動整合拒絕套用，請保留 override 並改用手動啟用或人工審閱整合；工具不修改它。全域或更深層 override、Claude 指令載入設定與排除仍需實機確認。

多檔追加不是跨檔原子交易。若中斷，核對原文備份及當前檔案，重新預覽；已存在的相同引用保留，其餘才追加，不自動 rollback。要撤回時，人工比較當前檔案與原文備份，只移除已審核的 UAML 引用／匯入，保留之後的新成果，避免直接用舊備份覆蓋整檔。

套用成功後開新對話，確認 Agent 確實讀到原生引用、條件觸發時讀共享入口並核對 Git。若未載入，使用上方手動提示；不以測試產生檔案當作 T01／T02 已通過。

## 交接與異常

在重要里程碑或使用者明確要求時，更新 State／Handoff 的實際內容及驗證結果，再執行 checkpoint --agent codex 或 claude-code；確認 CHECKPOINT_SAVED。切換 Agent 後重新恢復並核對當前檔案，不重用過時測試結果。Git commit／push 是另外的授權動作。

工具不可用時，入口提供人工 Markdown 降級方式；不自動安裝、不建立空 Vault、不自動核准 checkout。缺失／損壞／衝突先回報，原始成果保留。一般訊息無須掃描 Vault 或重寫記憶。

官方資料核對日期：2026-11-07。程式測試只能驗證產生檔案與共用資料契約，不能替代真實 Codex Windows／Claude Code 新對話驗收。
