# 架構設計

狀態：Phase 3 整體設計；2026-10-22 已實作身份／解析／Repo 保存恢復、checkpoint 補完、明確授權 Knowledge 新增／讀取／有界搜尋、精確／近似去重及單篇提案修訂。Agent 自動適配與跨筆記生命週期交易仍是計畫。資料欄位見 [Schema](DATA-SCHEMAS.md)，解析見 [Resolver](BINDING-RESOLVER.md)。

## 權威來源

| 資料 | 權威位置 | 其他位置允許內容 |
| --- | --- | --- |
| 專案狀態 | Repository PROJECT-STATE.md | 連結、hash、歷史備份 |
| 最近交接 | Repository HANDOFF.md | 連結、歷史備份 |
| 決策 | Repository decisions/ | 引用 |
| 共用技術知識 | Vault Knowledge 筆記 | ID、明示的摘錄與版本引用 |
| 綁定 | Repo Manifest 與 Vault 反向關聯共同驗證 | 本機核准紀錄 |
| 本機路徑／授權 | Registry | 不提交 Git |
| 搜尋索引 | 衍生快取 | 可刪除重建，不是權威 |

備份是歷史資料，不是第二份「目前版本」。分支各自帶著 Repo 記憶；Vault 反向索引不保存跨分支的單一最新進度。

## 建議使用者資料結構

```text
Repository/
  .uaml/project.yaml
  docs/memory/PROJECT-STATE.md
  docs/memory/HANDOFF.md
  docs/memory/checkpoint.json
  docs/memory/decisions/       # 必要時才建立

Vault/
  .uaml/vault.yaml
  UAML/Projects/<project_memory_id>/PROJECT.md
  UAML/Knowledge/<knowledge_id>.md

本機使用者資料目錄/
  registry.json
  backups/
  transactions/
  cache/
```

這些是未來使用 UAML 的目標結構，本次文件發布不初始化任何真實記憶或 Vault。既有 Vault 其他目錄及 .obsidian 不屬預設寫入範圍。

## 模組與資料流

```text
使用者／Agent
  → CLI
  → Git Root + Manifest
  → Registry + checkout grant
  → Vault ID + reverse link
  → State/Handoff + 必要知識
  → Git/實際檔案差異
  → 有來源與不確定性標記的 Recovery Report
```

| 模組 | 契約 |
| --- | --- |
| schemas | 嚴格解析與版本／欄位驗證，不執行資料 |
| paths | 根目錄與 canonical path，避免連結越界 |
| git_state | 唯讀 Git 觀察、快照與差異分類 |
| registry | 本機候選、位置、核准與安全更新 |
| binding | 純解析結果與診斷，不建立 Vault |
| recovery | 組合證據，不代替 Agent 的技術判斷 |
| project_memory | State／Handoff checkpoint |
| knowledge | 知識生命週期、儲存與查詢 |
| dedup | hash、Unicode 候選與條件差異 |
| storage | 鎖、expected hash、備份與交易紀錄 |
| adapters | 最小 Agent 入口，共用同一資料契約 |

核心不依賴 Codex／Claude SDK。搜尋與寫入必須通過同一範圍政策，不讓索引繞過授權。

## Recovery Report

必須包含身份、Binding 狀態、來源檔案及 revision/hash、目前 Branch/HEAD/Working Tree、記憶與實況差異、完成／未完成工作、Blockers、下一步及無法確認資訊。

恢復預設唯讀，不執行專案程式或歷史命令。Agent 先讀當前專案規範，再核對報告及相關實際檔案；歷史筆記不是高優先級指令。

有界投影已實作於 context.py：recover --compact 先取得兩份有界記憶全文，再以確定性的章節優先序配置輸出；預設 32 KiB、最小 8 KiB、最大 64 KiB，計入 JSON 排版與 LF。這是來源摘錄，不是語意推論。budget 與各 section 明示截斷／省略，來源 hash 與 checkpoint 判斷保留，不把截斷誤報成完整。普通 recover 保留原輸出契約，compact 不新增 Vault 掃描。

## Git 觀察

使用 [git-rev-parse](https://git-scm.com/docs/git-rev-parse) 識別 Root／worktree，不假設 .git 是資料夾；用 [porcelain status](https://git-scm.com/docs/git-status) 區分 staged、unstaged、untracked 與 conflict。處理 detached HEAD、無 HEAD、shallow clone 與 submodule 邊界。

| 差異 | 解讀 |
| --- | --- |
| 記錄 Commit 與目前一致 | 只代表未發現 Commit 差異，仍檢查 Working Tree |
| 記錄是目前祖先 | 可能落後，檢查相關檔案 |
| 分支分岔 | 不自動接續另一條工作線 |
| Commit 不存在 | 歷史不足或不匹配，標為未知 |
| Working Tree 不同 | 本地內容優先，不覆蓋 |
| 只有記憶檔更新 | 不誤認為功能程式碼改變 |
| 技術環境不同 | 歷史驗證不直接適用 |

保存前觀察到的 HEAD 是程式碼基準，不是包含未來 Handoff 的自我參照 Commit。指紋記錄排除項目與覆蓋範圍，排除記憶本身避免遞迴；沒有觀察的檔案不能宣稱一致。

離線 ahead/behind 只相對本機 tracking refs；遠端即時狀態標為 unknown。恢復不自動 fetch、reset、stash、checkout 或執行 external diff/textconv/fsmonitor。

## 搜尋與索引

只搜尋授權 Knowledge 根目錄；標題、摘要、分類與正文文字匹配，加上 OS、環境、版本、狀態篩選。回傳匹配原因、ID、來源與適用條件。索引失效時可有界掃描，標示是否完整，允許明確重建。

初步預算（待批准與測量）：普通對話零次自動 Vault 掃描／寫入；Binding 僅讀固定身份檔；恢復摘要預設最多 32 KiB；搜尋預設最多載入五篇完整候選。超出預算必須明示截斷與來源，不偽裝完整。

## 去重

1. 同 ID：更新既有筆記，核對 expected hash。
2. 同適用條件及內容 hash：返回既有 ID，阻止重建。
3. Unicode/CJK lexical 或字元 n-gram：只產生近似候選。
4. OS／版本／前置條件不同：不自動合併，可建立關聯或版本變體。
5. 否定語意與命令差異：列出實質差異供審查。
6. 索引不完整：先補足檢查，或保留為提案；不能宣稱確定沒有重複。

精確內容正規化只處理明確無語意差異（例如換行）；不移除版本、否定詞或任意標點來決定自動去重。新增的最終檢查在共同鎖內執行，避免並行建立同樣知識。

## Agent 適配

手動「恢復此專案」為必備。經批准可加入短的專案入口引用；Skills／Hooks 選配。不得複製兩套開發規範，或用 AGENTS.override.md 壓過既有規則。依實際 Claude 版本及 CLAUDE.md 載入情況決定薄適配。

基本協定：讀規範 → 唯讀恢復 → 核對來源／Git／檔案 → 回報缺口與下一步 → 重要事件或明確要求才保存。技術驗證由當前 Agent 在授權範圍內執行，不能把舊結果當成新結果。
