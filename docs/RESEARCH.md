# 原始碼研究與可行性

研究日期：2026-10-18（Asia/Taipei）。這份文件保存開發前研究，不是 UAML 功能測試報告。

## 證據範圍

Obsidian Mind 固定於 Commit [`fae7be467fc5e23bf9d51df7207d41f0c07e2754`](https://github.com/breferrari/obsidian-mind/commit/fae7be467fc5e23bf9d51df7207d41f0c07e2754)，提交時間台北 2026-10-18 07:34，manifest 宣告 10.0.0。

研究已閱讀文件、關鍵原始碼、部分測試程式碼，並核對上游 CI。沒有執行上游安裝、初始化或本機測試，沒有對真實 Vault 寫入。

歷史 ChatGPT 對話已讀取所有可取得頁面，但助理回答僅回傳引用標記，無法宣稱取得完整正文。產品需求以使用者本次完整規格為準，歷史探索不構成設計批准。初期網頁快取時點不同，重要上游判斷已改用固定 Commit 的 GitHub 內容。

## 實際架構與安裝

[README](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/README.md) 與 [ARCHITECTURE](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/ARCHITECTURE.md) 描述 Markdown Vault、Hooks、QMD、om MCP 四層；跨 Repo 存取的重要入口是 MCP。安裝／初始化可能寫入 Vault、個人化資料、Git 與索引，本次未執行。

[AGENTS.md](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/AGENTS.md) 中的 brain/work/org/perf 結構涵蓋較廣的個人知識管理。單一狀態權威、推論標註、易變事實加日期、保留 frontmatter、不擅改 .obsidian、不自動 commit 等原則適合 UAML；人物、績效與會議管理不納入。

[vault-manifest.json](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/vault-manifest.json) 區分 infrastructure/user content，包含 schema、搜尋根目錄、context budget 與版本指紋，但不是 UAML Portable Binding。

## Binding 差距

[mcp-caller.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/mcp-caller.ts) 使用 MCP roots、.om-project 名稱、資料夾名稱或 OM_CALLER 判斷 caller。沒有本案要求的 UUID＋Vault Registry＋checkout grant 完整契約。相關性 scope 不等於存取授權。

UAML 必須獨立設計穩定身份與本機信任，Remote／名稱只作定位提示，防止 Fork 複製 Manifest 後誤讀私人 Vault。

## Hooks、搜尋與 Windows

- [Codex hooks.json](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.codex/hooks.json) 包含 SessionStart、UserPromptSubmit、PostToolUse、Stop 與 commandWindows。這是配置證據，不是 Windows Desktop 全流程通過證據。
- [Claude settings](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/settings.json) 使用 shell walk-up 找 manifest；實際 shell、版本、信任與權限需驗證。
- [validate-write.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/validate-write.ts) 檢查寫入目標、frontmatter、wikilinks、筆記大小與 hygiene，並觸發 refresh。PostToolUse 屬寫後檢查，不能當成寫前安全攔截。
- [qmd-bootstrap.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.scripts/qmd-bootstrap.ts) 建立 collection/context、稀疏索引及 embeddings。UAML 將索引視為可重建衍生資料。
- [qmd.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/qmd.ts) 特別避開 Windows npm .cmd/.ps1 shim，解析 JS 入口再以 Node 執行，顯示 shell 差異的實際維護成本。
- [mcp-memory-bridge.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/mcp-memory-bridge.ts) 接合 memory core、可見性、QMD 排序與 Vault 查找。UAML 初版不需繼承整套依賴。

## 去重發現

[memory-similarity.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/memory-similarity.ts) 使用 lexical Jaccard，title/body 權重 0.6/0.4，duplicate 門檻 0.75、related 0.35，先比較部分 facets。

靜態推導：tokenizer 的 `/[^a-z0-9._/-]+/` 會移除中文；兩個空集合的 Jaccard 回傳 1，因此同 facets 的不同純中文筆記可能得到最高相似度。保留版本數字也不等於版本差異是硬門檻；移除否定 stopwords 可能遺失條件。

這是從函式推導的反例，尚未本機重現。[測試檔](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/tests/memory-similarity.test.ts) 有英文重述、不同主題、版本 token 與 facets 案例，讀到的範圍沒有 CJK 反例。UAML 應採 Unicode/CJK 候選、精確 hash 與環境硬條件；近似只提案。

## 寫入、安全及測試證據

[atomic-write.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/atomic-write.ts) 已使用 exclusive create、暫存替換、lock、重讀與 Windows 暫時錯誤重試。十秒鎖齡不能充分證明持有者死亡；不遵守鎖的外部編輯仍有競態。原子替換不等於跨檔交易、耐斷電或跨機同步一致。

[mcp-exposure.ts](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/lib/mcp-exposure.ts) 統一 private marker、讀取根目錄及 realpath/symlink containment；[測試](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/tests/mcp-exposure.test.ts) 用臨時 Vault 驗證讀取表面。UAML 借鏡集中政策，但不採過廣的預設授權。

[supersede race 測試](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.claude/scripts/tests/memory-supersede-race.test.ts) 以四個程序各寫五十輪，檢查二百個標題保留，具有實際並行測試價值。

[CI run 39079564150](https://github.com/breferrari/obsidian-mind/actions/runs/39079564150) 的七個 jobs 已核對成功：Ubuntu/macOS/Windows × Node 22/24，以及 Ubuntu without-QMD。[配置](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/.github/workflows/test.yml) 一般組使用 QMD 2.8.3、typecheck 與 npm test。未完整分析所有 job logs；CI 成功不能取代 UAML、本機或真實 Agent 驗收。

## 採用分類

| 分類 | 建議 |
| --- | --- |
| 採用理念 | Markdown、單一權威、來源日期、可重建索引、純核心與 IO 分離、統一讀取政策 |
| 簡化實作 | context budget、lexical 候選、寫前驗證、鎖＋expected hash＋備份 |
| 未來選配 | QMD、MCP、Hooks、語意排序、Obsidian UI、知識圖譜 |
| 不納入 MVP | 每訊息分類、每輪整理、背景 embeddings、人物績效、整套 Vault upgrader |
| 風險 | 名稱當身份、scope 當權限、過廣 exposure、寫後驗證當安全閘、時間型鎖接管、中文去重 |

上游採 [MIT](https://github.com/breferrari/obsidian-mind/blob/fae7be467fc5e23bf9d51df7207d41f0c07e2754/LICENSE)；重用實質程式碼需保留通知。本次沒有將上游程式碼匯入 UAML。

## 官方 Agent 能力矩陣

| 能力 | Codex Windows | Claude Code | UAML 方針 |
| --- | --- | --- | --- |
| 本地 Markdown／Git | 受目前工具及權限限制 | 受目前工具及權限限制 | 基本入口 |
| 指令檔 | AGENTS.md 有階層及大小限制 | CLAUDE.md；新版有條件支援 AGENTS.md | 保留既有規範，偵測載入結果 |
| Skills | 官方支援按需載入 | 可另做適配 | 選配 |
| Hooks | 官方已有生命週期 Hooks | 官方已有生命週期 Hooks | 不作基本依賴 |
| 每次新對話自動恢復 | 依入口、信任與版本 | 同左 | 真實流程驗收 |
| 外部 Vault 寫入 | 可能超出 sandbox 可寫範圍 | 依環境與權限 | 最小授權、唯讀降級 |

官方來源（研究日期快照，未來開發須重新核對版本）：

- [Codex Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)：原生 Windows／PowerShell、Skills 及受限檔案／網路權限。
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：搜尋層級、override 與大小限制。
- [Skills](https://learn.chatgpt.com/docs/build-skills)：按需揭露，隱式選用不是保證每次觸發。
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)：生命週期事件及非 managed hooks 信任流程。
- [Claude memory](https://code.claude.com/docs/en/memory)：AGENTS.md 直接載入需要 v2.1.277+，且受既有 CLAUDE.md／CLAUDE.local.md 等條件影響。
- [Claude Hooks](https://code.claude.com/docs/en/hooks) 與 [Windows setup](https://code.claude.com/docs/en/setup)：原生與 WSL 的 shell／sandbox 能力須分開看待。
- [Obsidian Vault](https://help.obsidian.md/vault)：本地資料夾可作 Vault，不要求 Obsidian 持續開啟。

## 可行性與仍須實測

ID、Registry、格式驗證、Git 快照、文字搜尋與合作寫入衝突可用一般本機程式實作。理解交接、判斷下一步與技術適用性依賴 Agent。新對話入口、外部 Vault 權限、雙向接管、第二台乾淨 Windows 環境必須實測。

Windows 重點：中文／空白／長路徑、PowerShell 與 Git Bash／WSL、檔案佔用、CRLF、junction/symlink、UNC、大小寫別名、worktree 的 .git 檔案、同步衝突。v0.1 建議先保證本機檔案系統，不宣稱網路磁碟與跨機同步寫入一致。
