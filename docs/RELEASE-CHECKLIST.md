# 建置與發布前檢查

目前產品仍為 `0.1.0.dev0`，沒有正式 release。本指南建立可安裝性證據，不是發布授權；CI 不 push、上傳 PyPI、建立 tag 或 GitHub release。

## 建置及離線安裝驗證

僅在專案隔離環境安裝建置依賴；runtime 仍只有 PyYAML，dev extra 的 build／setuptools 不會強制安裝到一般使用者環境。

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m build --no-isolation
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest .uaml-local/wheelhouse 'PyYAML>=6.0.2,<7'
.\.venv\Scripts\python.exe scripts/verify_distribution.py --dist dist --wheelhouse .uaml-local/wheelhouse
```

`build` 預設先建 sdist，再從該 sdist 建 wheel；本地 --no-isolation 使用已準備的 dev 環境。這可檢查是否漏掉建置必需檔案。[PyPA 建置說明](https://packaging.python.org/en/latest/tutorials/packaging-projects/) 提供格式背景。重跑前使用只含本次版本的一個 wheel／一個 tar.gz 的新目錄（可改 --outdir／--dist）；驗證器不清除既有成果或挑選模糊的多版本檔案。

驗證器先檢查檔案路徑／大小／重複項、全部 uaml 模組、Name／Version／Requires-Python／runtime dependencies、MIT 授權原文、console entry point，以及 sdist 的程式碼／測試／指南。拒絕明顯機器私有目錄及 Registry 檔；這不是任意未知秘密的 DLP，也不是執行不可信套件的 sandbox。

接著建立臨時 venv，停用 user site／PYTHONPATH／舊 UAML_HOME／pip index，僅從指定本地 wheelhouse 安裝 wheel 與 runtime。確認 uaml 的 module path 在新 venv、版本及 console script 正確，執行 pip check、隔離示範與完整測試。測試從 Repository 載入測試程式，uaml runtime 來自新 wheel；不使用 editable source。所有示範／Repo／Vault／Registry 為臨時 fixtures。

DISTRIBUTION_VERIFIED 才表示本次步驟成功，並列出兩份 artifact SHA-256；任一步失敗回傳 DISTRIBUTION_FAILED／非零 exit。pip download 與建置工具安裝需要套件來源，實際乾淨 venv 的安裝／驗證流程不連 index。驗證結束清理工具自己建立的臨時 venv；不刪 dist、wheelhouse 或使用者資料。

## GitHub Actions

[CI workflow](../.github/workflows/ci.yml) 在 main／codex 分支 push、pull_request 或手動觸發，矩陣為 Windows hosted runner／Ubuntu × Python 3.11／3.12。它建置 artifact，下載 runtime wheelhouse，再執行同一離線安裝驗證與完整測試，不重複執行另一套等價 suite。

官方 checkout／setup-python Actions 以 SHA 固定（已核對 v7 公開標籤），權限只有 contents: read，checkout 不持久保存憑證。沒有 secrets、發布憑證、安裝後背景服務或其他 Agent 設定。官方來源：[checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)。更新 SHA 前需核對官方版本及 runner 相容性。

Windows hosted runner 不等於使用者的 Windows 11；Linux suite 的 Windows 專用案例預期 skip，仍需分開記錄結果。CI 成功不替代真實 Codex／Claude 對話、第二台使用者環境、ACL 全面強化或實際 GitHub／Vault 同步。未取得 run 結果前只可記錄「workflow 已建立」，不能宣稱 CI 通過。

## 正式版本閘門

- 將 [驗收表](ACCEPTANCE-TESTS.md) 的 required 情境逐項補齊實機證據；unknown／not_run 不視為 passed。
- 核對 [Roadmap](../ROADMAP.MD)、已知限制、公開資料及授權；核准版本後同時更新 pyproject 與 uaml.__version__，再重新建置驗證。
- 對要發布的確切 Commit 取得完整 CI 與 artifact hash；確認 artifact 沒有私有 Registry／Vault／計畫／憑證。
- 更新 CHANGELOG，確認安裝、接管、遷移、故障排除及安全說明符合實際行為。
- 只有取得明確發布授權後，才執行 tag、release 或 PyPI 上傳；本輪不包含這些動作。
