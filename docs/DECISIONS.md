# 決策狀態與批准邊界

本文件區分使用者明確需求與建議實作。2026-10-18 的文件 Commit／Push 不代表 Phase 5 授權；2026-10-22 使用者另行授權選取重要項目實作雛形及完成後 Commit／Push。該授權仍不表示完整 MVP 或所有選配設計已批准。

## 本輪採用（2026-10-22）

在建立雛形的授權內，採用 D01–D07 的必要子集及 D10 的保證邊界：Python/PyYAML、YAML/JSON、Repo 權威、UUID、獨立 Vault 子樹、checkout 反向索引讀取授權、合作鎖／hash／備份／checkpoint。未完成完整 M0、ACL 強化、repair、一般 Vault 寫入或全套提案介面，不把初步採用改標為全部驗收完成。

目前僅支援標準三個 docs/memory 路徑，防止 Manifest 導向覆寫其他專案檔。D08 知識去重、D09 自動適配、D11 知識生命週期與 D12 完整效能預算仍待實作／確認；恢復正文目前每篇最多 12 KiB，明示截斷，不宣稱整份 JSON 一定低於 32 KiB。

### 優先項目進展

使用者已明確要求繼續三項優先工作並逐項 Commit／Push。第一項已加入 checkpoint repair；第二項採用 Knowledge 的嚴格 Schema 與單層有界文字搜尋，不新增索引依賴。知識存取預設 none，由 trust --knowledge 明確設定 read/write；write 仍只限 Knowledge 子樹。這不代表 Agent 自動適配或完整 MVP 已完成。

第三項已採用 D08 的精確去重與近似只提案，以及單篇 propose/apply、原檔／payload／目錄 hash 與備份。D11 已實作資料層驗證與修訂 freshness 檢查，不宣稱驗證技術解法本身。D09 Agent 自動適配、D12 全面效能驗收及跨筆記 supersession 仍待後續；32 KiB 全報告預算尚未完成。

## 已確認的產品邊界

- 正式名稱 Universal Agent Memory Lite（UAML），首版目標 v0.1.0，無舊版相容要求。
- Local-first、Markdown-first、portable、agent-agnostic、non-invasive。
- Repository–Vault Portable Binding 為核心功能，不可省略。
- Windows 11、Codex、Claude、Git/GitHub、Obsidian／Markdown 為首批目標。
- 不將未保存內容當成可恢復；不把歷史記憶當最新事實。
- 基本能力不得強制依賴 MCP、QMD、向量 DB、模型或背景服務。
- 保留既有規範；不未經批准修改其他 Agent 全域設定。
- 16 項驗收不得以降低要求或隱藏錯誤取得通過。
- Phase 5 須在 Phase 1–4 審核後取得明確授權。

## 原建議與後續決策索引

| ID | 選擇 | 建議與理由 |
| --- | --- | --- |
| D01 | 核心語言／依賴 | Python 3.11+、Git、PyYAML；低依賴跨平台檔案工具 |
| D02 | 控制格式 | YAML Manifest/frontmatter；JSON Registry/checkpoint；嚴格限制解析 |
| D03 | 專案狀態權威 | v0.1 固定 Repository，Vault 不複製進度 |
| D04 | Vault 佈局 | .uaml/vault.yaml＋獨立 UAML/ 子樹，避免干擾既有筆記 |
| D05 | 穩定身份 | 隨機 UUID；名稱／Remote 只作提示 |
| D06 | Fork 與信任 | 每個新 checkout 一次核准，重要 Binding 變更重新確認 |
| D07 | 安全更新 | 提案／明確操作＋expected hash＋合作鎖＋備份＋checkpoint |
| D08 | 去重 | 精確重複阻止新增；近似只提案；條件差異保留 |
| D09 | 適配 | 手動恢復必備；專案短引用／Skills 選配；Hooks 延後 |
| D10 | 保證範圍 | 本機檔案系統合作程序；不承諾跨機同步／非合作編輯完全一致 |
| D11 | 驗證生命週期 | verified 需證據與環境；修改步驟／條件後重新驗證 |
| D12 | 效能預設 | 32 KiB 摘要、五篇完整候選、普通對話零自動 Vault 掃描 |
| D13 | 歷史材料限制 | 以使用者完整規格定稿，未取得的歷史助理回答不作依據 |

既有專案已包含 MIT LICENSE；本次保留。若重用上游程式碼，仍須逐項處理通知，不因專案同為 MIT 就省略來源要求。

## 需要實機而非討論決定的事項

- Windows Codex 桌面版入口是否可靠載入，外部 Vault 權限如何授予。
- 實際 Claude 版本與 CLAUDE.md／AGENTS.md 載入規則。
- 真實雙向交接、第二台乾淨 Windows 恢復。
- 檔案佔用、ACL、junction、中文路徑及暫存替換。
- 搜尋與摘要預算的實際表現。

## 未來決策記錄方式

批准後記錄決策 ID、日期、批准範圍、取捨與影響文件；不把「已寫進文件」改標為「已批准」。重大變更回到需求及驗收追溯，避免只改一份摘要造成矛盾。
