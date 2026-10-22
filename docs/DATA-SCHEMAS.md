# 資料格式草案

狀態：Phase 3 設計契約，2026-10-22 已實作身份、Registry、反向索引、專案記憶與 Knowledge 的限制型驗證。以下是合成範例，不是實際使用者身份、測試或 Git 證據。

雛形額外限制：每份檔案最多 256 KiB、YAML 深度最多 16、extensions 只能是空物件、專案記憶僅接受下列標準三個路徑。不支援自訂位置或未知擴充的寫入，避免擴大範圍。

## 共通約束

- schema_version 與產品版本分開；首版接受 1，沒有舊 UAML 相容包袱。
- project_id、vault_id、project_memory_id、knowledge_id、snapshot_id 使用隨機 UUID。
- 名稱與 Remote URL 不生成 ID；ID 不是密碼或授權。
- UTF-8；寫出 LF，讀取容忍 CRLF；時間 RFC 3339 並帶時區，建議 UTC。
- revision 為正整數，但衝突以原始內容 SHA-256 為準，不能單靠 revision 判定跨機最新。
- 嚴格欄位；擴充集中 extensions。禁止重複鍵、任意 tags、aliases、merge keys、多文件與過深／過大 YAML。
- 未知 Schema 不自動寫入或升級；可明示風險後提供原始文字唯讀檢視。
- Manifest 內路徑是指定根目錄內的相對檔案路徑，使用 /；拒絕 ..、絕對路徑、磁碟代號、UNC、URI、NUL 與連結越界。
- ID 配對、Schema 合法、內容完整與技術正確是不同檢查，不互相替代。

## Repository .uaml/project.yaml

```yaml
schema_version: 1
kind: uaml_project
revision: 1
project:
  id: "0f3c12d4-9c72-4ac1-ae61-a233e8279c01"
  name: "ExampleProject"
binding:
  vault_id: "3e9d7abc-44d0-4f73-bb8b-41dc321a8281"
  project_memory_id: "a2177d6e-d543-46dd-9975-0c8ff81010e2"
memory:
  authority: repository
  project_state: "docs/memory/PROJECT-STATE.md"
  handoff: "docs/memory/HANDOFF.md"
  checkpoint: "docs/memory/checkpoint.json"
repository:
  canonical_url: "https://github.com/example/example-project"
extensions: {}
```

kind、revision、project、binding、memory 必填；authority 在 v0.1 固定 repository。三個 memory 檔案路徑必須不同。canonical_url 選填，只作提示，不能含憑證或敏感參數；私人 Repo 名稱也可能不適合公開。檔案不得包含本機絕對路徑、Token 或機器秘密。

## Vault .uaml/vault.yaml

```yaml
schema_version: 1
kind: uaml_vault
revision: 1
vault:
  id: "3e9d7abc-44d0-4f73-bb8b-41dc321a8281"
  name: "Engineering Knowledge"
layout:
  projects: "UAML/Projects"
  knowledge: "UAML/Knowledge"
extensions: {}
```

名稱／位置可變，ID 不變。備份或同步副本保留 ID；獨立新 Vault 需要明確分離流程，不因複製自動換 ID。

## 反向索引 PROJECT.md

位置由 layout.projects＋project_memory_id 決定。frontmatter：

```yaml
schema_version: 1
kind: project_link
revision: 1
project_id: "0f3c12d4-9c72-4ac1-ae61-a233e8279c01"
project_memory_id: "a2177d6e-d543-46dd-9975-0c8ff81010e2"
vault_id: "3e9d7abc-44d0-4f73-bb8b-41dc321a8281"
project_name: "ExampleProject"
state_authority: repository
repository_url: "https://github.com/example/example-project"
knowledge_ids: []
```

正文說明專案與關聯知識，引用 Repository 權威，不保存另一份目前進度。跨位置連結以 ID 與相對位置解析，不依賴 Vault 顯示名稱或本機 obsidian:// URL。

## 本機 registry.json

```json
{
  "schema_version": 1,
  "revision": 4,
  "vaults": [{
    "vault_id": "3e9d7abc-44d0-4f73-bb8b-41dc321a8281",
    "candidates": [{
      "candidate_id": "c52bccf3-7ba9-4721-9de6-3ec8d8ee9101",
      "path": "D:\\Notes\\Engineering",
      "last_verified_at": "2026-10-18T01:00:00Z"
    }],
    "selected_candidate_id": "c52bccf3-7ba9-4721-9de6-3ec8d8ee9101"
  }],
  "checkout_grants": [{
    "repository_root": "D:\\Code\\ExampleProject",
    "git_directory": "D:\\Code\\ExampleProject\\.git",
    "remote_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
    "binding_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
    "vault_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
    "project_id": "0f3c12d4-9c72-4ac1-ae61-a233e8279c01",
    "vault_id": "3e9d7abc-44d0-4f73-bb8b-41dc321a8281",
    "project_memory_id": "a2177d6e-d543-46dd-9975-0c8ff81010e2",
    "access": "read",
    "scope": "project_link",
    "approved_at": "2026-10-18T01:00:00Z"
  }]
}
```

範例 hash 以零填充，實際由程式計算。grant 綁定 canonical checkout/Git 位置、Remote 設定 hash、Manifest 原始 hash 與 Vault 身份檔 hash；重要內容改變後重新核准，不保存可能含憑證的原始 Remote URL。候選 ID 為本機 UUID。scope 固定 project_link、access 固定 read；可選 knowledge_access 為 none/read/write，省略視為 none，只對 layout.knowledge 有效，不是整個 Vault 的授權。

Registry 含本機路徑，禁止提交 Git；新電腦重新註冊，而非盲目套用舊 Registry。

## Project State／Handoff

State 保存整體狀態、里程碑、未完成事項及決策索引；Handoff 保存最近接手上下文。共通 frontmatter 範例：

```yaml
schema_version: 1
kind: handoff
project_id: "0f3c12d4-9c72-4ac1-ae61-a233e8279c01"
snapshot_id: "51c7434f-1764-4325-8684-ec5bd4efdf91"
revision: 3
updated_at: "2026-10-18T01:00:00Z"
source_agent: "codex"
git:
  branch: "feature/example"
  head: null
  object_format: "sha1"
  working_tree: "dirty"
  upstream: null
  remote_freshness: "unknown"
  working_tree_fingerprint: null
```

State 的 kind 為 project_state。branch 在 detached HEAD 可 null；head 在尚無 Commit 時可 null，讀取失敗須另報錯而非冒用 null。object_format 辨識 sha1/sha256。working_tree 為 clean/dirty/conflicted/unknown，未知須有原因。雛形增加可選 working_tree_fingerprint：排除 .uaml 與三個記憶檔，雜湊變更檔索引資訊及目前內容；遇到連結、子模組、可能憑證檔、不可讀或超出預算時為 null 並報告不完整。不把它當整個執行環境的一致性證明。

Handoff 正文必備：當前任務、已完成、未完成、主要變更檔案、Git／Working Tree 快照、測試驗證、Blockers、下一步、風險與假設、未保存／無法恢復內容。無內容寫「無」，未知寫原因。

每項驗證包含方法、時間、passed/failed/not_run/unknown、對應 Commit 與 dirty 狀態、證據位置或摘要、未執行原因。命令是資料，不自動執行。

## checkpoint.json

必填 schema_version、project_id、snapshot_id、updated_at、files。files 是路徑與 SHA-256 對應，必須精確涵蓋同批 State/Handoff；hash 使用完成寫入檔案的原始位元組，不含 checkpoint 自己。兩份 frontmatter 的 snapshot_id 必須相同。

checkpoint 是完整性標記，不保存第三份進度。先準備／替換 Markdown，最後公布 checkpoint；詳見 [安全設計](SECURITY-AND-RISKS.md)。

## 本機 checkpoint journal v2

`transactions/<snapshot_id>.json` 保存 schema_version=2、repository_root、project_id、binding_fingerprint、status、checkpoint、entries、previous_hashes、previous_checkpoint_hash。每個 entry 為標準三檔之一，包含 path、before_hash、after_hash、before_blob、after_blob；payload 只能是同目錄 `<snapshot_id>.<0..2>.before/after`。先保存完整 payload 再公布 prepared，完成後改為 complete。檔案在 Registry 本機目錄，不提交 Git。

repair 只接受當前身份／Manifest 指紋及精確三檔，驗證 payload、snapshot 與 checkpoint hash。plan_hash 同時綁定 journal 原始 hash 及三檔目前 hash；變更後必須重新預覽。舊 v1 沒有 payload，不自動修復。

## Shared Knowledge

```yaml
schema_version: 1
kind: knowledge
id: "51c5e4ef-5f4d-4498-a6f3-7d44ef8c31f0"
revision: 1
title: "某環境的工具鏈安裝經驗"
category: "development-environment"
status: experimental
source_project_ids: ["0f3c12d4-9c72-4ac1-ae61-a233e8279c01"]
created_at: "2026-10-18T01:00:00Z"
updated_at: "2026-10-18T01:00:00Z"
applicability:
  os: ["windows"]
  architecture: ["x86_64"]
  components: []
verification:
  checked_at: null
  evidence: []
related_ids: []
supersedes: []
```

正文包含摘要、適用條件、步驟／程式碼、驗證方法結果、限制、失敗方案、來源關聯。components 應記錄工具名稱及版本條件，未知不得推論為不限版本。

verified 必須有適用環境、時間與證據；變更步驟或適用條件後重新驗證。deprecated 必須有原因；superseded 必須有替代 ID，並維持正反引用一致。專案可引用 ID＋revision/hash，辨識後續變更。空環境不表示通用適用。

已實作的 components 是 `{name, version}` 物件列表，名稱不重複；applicability 可選 conditions 字串列表。verification.evidence 是 `{method, result, source?}` 物件列表，checked_at 帶時區。deprecated 額外要求 deprecation_reason；superseded 要求 superseded_by UUID。新增匯入只接受 active 狀態、revision=1、目前 Project 為 source，禁止用 supersedes 改寫其他筆記生命週期；跨筆記 supersession 一致性交易留待後續實作。

## 本機獨立 Fork 計畫 v1

`forks/<fork-id>.json`：schema_version=1、kind=project_fork、id、git_identity、target_vault_id、target_vault_path、vault_hash、source_project_id、link_hash、entries。每個 entry 為標準四檔之一，順序為 State、Handoff、checkpoint、Manifest，保存 path／before_hash／after_hash；相同索引的 before/after 檔與 link payload 必須匹配。所有原內容封存在本機，不提交 Git。

計畫要求新的 Project／Memory ID；新反向索引 knowledge_ids 必須為空。套用只接受目標目前 hash 為 before 或 after，最後切換 Manifest，可用同一計畫續做。它不自動匯入舊狀態、Canonical URL、私人知識或 checkout grant；不將 ID 視為授權。

## 本機知識提案 v1

`proposals/<proposal-id>.json`：schema_version=1、kind=knowledge_proposal、id、knowledge_id、context、before_hash（新增為 null）、after_hash、catalog_hash、similar。相同 ID 的 `.md` 保存 after-image。context 綁定 checkout Git 身份、Manifest 與所選 Vault／Knowledge 路徑；catalog_hash 為排序後所有已驗證筆記 ID＋原始 hash。plan_hash 是 JSON 原始位元組 hash，套用前必須相符。

修訂保留 id、created_at、既有來源專案，revision 恰加一，updated_at 不倒退；包含當前修改專案作為來源。步驟或 applicability 變更且仍為 verified 時，checked_at 必須比舊驗證更新並有有效證據，否則拒絕。單篇提案不可改寫 supersession 關係。

精確去重 key 包含標題、分類、換行正規化正文、適用條件、狀態、驗證證據及關聯。ID、revision、建立／更新／驗證時間與來源 Project 是 provenance，不作為產生第二份權威的理由；發現重複只回傳既有 ID，不合併新 provenance。近似以 Unicode/CJK tokens 的標題 0.4／正文 0.6 Jaccard、0.65 門檻提出候選；不同 OS／架構／元件版本／conditions 不納入同組。這是保守文字候選，不能證明語意相同。
