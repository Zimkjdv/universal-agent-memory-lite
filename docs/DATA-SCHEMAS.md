# 資料格式草案

狀態：Phase 3 設計提案，不是已實作的驗證器。以下是合成範例，不是實際使用者身份、測試或 Git 證據。

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
      "candidate_id": "local-copy-1",
      "path": "D:\\Notes\\Engineering",
      "last_verified_at": "2026-10-18T01:00:00Z"
    }],
    "selected_candidate_id": "local-copy-1"
  }],
  "checkout_grants": [{
    "repository_root": "D:\\Code\\ExampleProject",
    "project_id": "0f3c12d4-9c72-4ac1-ae61-a233e8279c01",
    "vault_id": "3e9d7abc-44d0-4f73-bb8b-41dc321a8281",
    "project_memory_id": "a2177d6e-d543-46dd-9975-0c8ff81010e2",
    "access": "read",
    "approved_at": "2026-10-18T01:00:00Z"
  }]
}
```

此簡化範例展示定位及授權分離。正式 grant 還必須保存經核准的 Binding 重要欄位指紋、Git 位置及 Remote 提示；完整欄位在 M0 固定。候選 ID 僅在本機有意義，不建立新的邏輯 Vault 身份。grant 應包含允許讀寫的子範圍，不將整個 Vault 隱含公開。

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
```

State 的 kind 為 project_state。branch 在 detached HEAD 可 null；head 在尚無 Commit 時可 null，讀取失敗須另報錯而非冒用 null。object_format 不硬限 SHA-1；應辨識實際 Git 格式。working_tree 為 clean/dirty/conflicted/unknown，未知須有原因。

Handoff 正文必備：當前任務、已完成、未完成、主要變更檔案、Git／Working Tree 快照、測試驗證、Blockers、下一步、風險與假設、未保存／無法恢復內容。無內容寫「無」，未知寫原因。

每項驗證包含方法、時間、passed/failed/not_run/unknown、對應 Commit 與 dirty 狀態、證據位置或摘要、未執行原因。命令是資料，不自動執行。

## checkpoint.json

必填 schema_version、project_id、snapshot_id、updated_at、files。files 是路徑與 SHA-256 對應，必須精確涵蓋同批 State/Handoff；hash 使用完成寫入檔案的原始位元組，不含 checkpoint 自己。兩份 frontmatter 的 snapshot_id 必須相同。

checkpoint 是完整性標記，不保存第三份進度。先準備／替換 Markdown，最後公布 checkpoint；詳見 [安全設計](SECURITY-AND-RISKS.md)。

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
