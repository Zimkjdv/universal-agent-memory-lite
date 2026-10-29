# 跨電腦與本地資料夾遷移

UAML 重新定位已保存的 Repository／Vault；它不複製資料、不自動授權新 checkout、不還原未保存的對話或完整執行環境。以下是目前可執行的流程；第二台真實環境驗收仍未完成。

## 先檢查來源

在來源 Repository 使用已安裝的 CLI，Registry 路徑由該電腦設定；--registry 如有需要，放在子命令之前：

```powershell
uaml --repo . --json migration check --mode github
uaml --repo . --json migration check --mode local
# 需要連帶檢查共用知識時，先有明確的 Knowledge read/write grant
uaml --repo . --json migration check --mode local --knowledge
```

check 唯讀。MIGRATION_CHECKED exit 0 表示本次來源檢查未發現需處理問題；MIGRATION_REVIEW_REQUIRED exit 1 表示須先審查 diagnostics。它檢查身份、完整 checkpoint、必填章節、Git 與記憶差異、未完成本機 journal、疑似已追蹤的私有 Registry／artifact 路徑；不顯示筆記正文。只含記憶／UAML 入口變更的祖先 Commit 可解釋保存前 HEAD 與目前 HEAD 不同，程式碼／branch／working content 差異仍需核對。

--knowledge 才使用既有 grant 掃描已授權 Knowledge，檢查關聯與 pending 狀態；省略時明示 NOT_REQUESTED，不代表知識完整或沒有未完成交易。知識掃描沿用 200 entries／16 MiB 上限，私有 checkpoint journal 預檢最多 1024 entries；超限或損壞會要求審查。

## GitHub Clone 模式的位元組保護

checkpoint 使用原始 bytes 的 SHA-256。Git 的自動換行、filter 或 encoding 轉換可能使 Clone 後檔案與已保存 hash 不符。先預覽以下可選規則：

```powershell
uaml --repo . --json migration rules
uaml --repo . migration rules --apply --expect-plan '<plan-hash>'
```

只建立 .uaml/.gitattributes 與 docs/memory/.gitattributes，對四個 UAML 資料檔使用 -text；原始 Markdown 仍可直接編輯。依 [Git 官方定義](https://git-scm.com/docs/gitattributes)，unset text 停用 checkin／checkout 換行轉換。根目錄 .gitattributes、其他檔案與 Git 全域設定不變；目標已有不同內容時拒絕覆蓋，請人工審查原規則，不為通過預檢而刪除它們。

預覽綁定目前 Manifest、checkout／Remote、目標內容與規則 hash；--apply 必須精確 --expect-plan。部分建立中斷可重新預覽，已相同檔案保留。工具不 stage／commit／push，也不執行 renormalize。GitHub 預檢只自動認證這兩份已提交的標準規則；其他等效自訂規則需人工驗證，保守回報 BYTE_RULES_UNVERIFIED。另檢查目前 Git attributes 沒有重新啟用 text／filter／working-tree-encoding。

建議先審查並提交程式碼與規則，再更新 State／Handoff、checkpoint，最後提交四份記憶檔並 push。GitHub 預檢要求四檔的實際 bytes 等於 HEAD，工作樹無未提交內容，且本機 tracking ref 與 HEAD 一致。tracking ref 不是即時 GitHub 證據：工具不 fetch 或連線，remote freshness 永遠為 unknown，仍需確認真正 Push 結果。

## 模式 A：GitHub Repository＋Vault

1. 在來源完成預檢、保存及明確授權的 commit／push，確認正確分支與 Commit。
2. 在新電腦 Clone 該 Repository，另行取得正確且同步完成的 Vault。Vault ID 保留，名稱與路徑可改。
3. 安裝 UAML 到新電腦的隔離環境，參見 [INSTALL](../INSTALL.md)。不複製舊電腦的 checkout grants 作為授權。
4. 只需一次提供該電腦的新 Vault 路徑：

```powershell
uaml vault register 'E:\Notes\MyVault'
uaml --repo 'D:\Code\MyProject' --json resolve
# 審查 Project／Vault／Memory IDs 與反向索引後核准新 checkout
uaml --repo 'D:\Code\MyProject' project trust
uaml --repo 'D:\Code\MyProject' --json recover --compact
uaml --repo 'D:\Code\MyProject' --json validate
```

新機 Registry 放在 Repository／Vault 之外，使用預設 OS 位置或明確 --registry／UAML_HOME。register 不初始化 Vault；第一次 resolve 尚未核准時拒讀私人記憶是正常行為。若要查詢知識，另行 project trust --knowledge read，並使用 validate --knowledge／migration check --knowledge 核對。

5. 核對目前 Git、實際檔案、工具及版本，再讓新 Agent 使用 [接管入口](AGENT-GUIDE.md)。後續同一已核准 checkout 可沿用 Registry 定位，不重填路徑。

## 模式 B：本地 Repository＋Vault

使用 --mode local；它允許已保存的 staged／unstaged／untracked 工作，記錄當前 Git 差異，且不要求記憶已提交到 HEAD。自行完整保留必要檔案、Git metadata 與正確 Vault，目的地重新 register／trust 後恢復。工具不替你選擇複製工具、不忽略或覆蓋未提交成果。

linked worktree 的 .git 可能指向外部 Git 目錄；單獨複製該資料夾不足，預檢回報 EXTERNAL_GIT_DIRECTORY，應先建立完整獨立 checkout 或用已審查的方式連同必要 Git metadata 搬遷。ignored 檔案、虛擬環境、未保存的檔案及外部服務不由預檢重建，依目前環境需求另行取得及驗證。

## 缺失、搬遷與衝突

Vault 找不到時，以 register／relocate 重新定位原 ID；不建立空白替代 Vault。多副本分歧先 compare／select 審查，流程見 [Binding Resolver](BINDING-RESOLVER.md)。獨立 Fork 使用 project fork，不能把複製的 ID 當私人記憶授權。

pending checkpoint 或知識替代交易應在來源完成後才搬遷。私有 journal、before/after payload、備份不屬公開 Git 中繼資料；目的地若只有 pending Vault 而沒有原私有計畫，需人工核對來源與備份，不能直接刪標記冒充修復。普通新機恢復不要求攜帶舊 Registry；尚未完成的交易則不能靠穩定 ID 憑空還原。

測試以本機臨時 bare remote、core.autocrlf=true Clone、新 Registry／不同 Vault 路徑，以及本地完整複製驗證資料契約。這不等於第二台 Windows、真實 GitHub 網路同步或 Agent 對話已通過。
