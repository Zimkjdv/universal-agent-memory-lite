# 決策狀態與批准邊界

本文件區分使用者明確需求與建議實作。文件整理／Commit／Push 已獲授權，**不代表 Phase 5 開發授權或所有設計已被批准**。

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

## 待批准的具體建議

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
