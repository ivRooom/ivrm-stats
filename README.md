# IVRM Status Console

`stats.ivrm.jp` で公開する、ivRooom Minecraftサーバー向けの静的運用ダッシュボードです。

## 目的

- サーバーのオンライン状態を最初に判断できる
- CPU、メモリ、プレイヤー数の推移を確認できる
- バックアップとStats収集タイマーの異常を見落としにくくする
- OCI内の既存JSON APIを維持したまま、UIをGitHubで管理する

## データソース

本番ではOCI上のcollectorが生成する次のファイルを読み込みます。

```text
/api/current.json
/api/history.json
```

ローカル開発やAPI障害時には、フロントエンド内蔵のデモデータを使用します。

## ローカル確認

ビルド不要です。

```bash
python3 -m http.server 4173
```

ブラウザで `http://localhost:4173` を開きます。

## 検証

```bash
python3 scripts/validate.py
node --check assets/app.js
bash -n scripts/deploy-oci.sh
bash -n scripts/rollback-oci.sh
```

## OCIへ手動デプロイ

OCI上でこのリポジトリをcloneまたはpullした後に実行します。

```bash
./scripts/deploy-oci.sh
```

既存UIは以下へ退避され、`/opt/ivrm/www/stats/api/` は保持されます。

```text
/opt/ivrm/www/stats.ui-backup-YYYYMMDD-HHMMSS
```

ロールバック：

```bash
./scripts/rollback-oci.sh /opt/ivrm/www/stats.ui-backup-YYYYMMDD-HHMMSS
```

## GitHub Actionsからデプロイ

`Deploy to OCI` workflowは手動実行です。GitHub Environment `production` と次のRepository Secretsを設定します。

| Secret | 内容 |
|---|---|
| `OCI_HOST` | OCIインスタンスのホスト名またはIP |
| `OCI_USER` | 通常は `opc` |
| `OCI_SSH_KEY` | デプロイ用Ed25519秘密鍵 |
| `OCI_KNOWN_HOSTS` | `ssh-keyscan` で取得したknown_hosts行 |

本番workflowはUIだけを更新し、collectorが生成するAPIデータを削除しません。

## ディレクトリ

```text
.
├── index.html
├── assets/
│   ├── app.js
│   ├── favicon.svg
│   └── styles.css
├── scripts/
└── .github/workflows/
```
