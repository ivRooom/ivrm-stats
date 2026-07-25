# ivRooom Status

`stats.ivrm.jp` で公開する、ivRooom公式の利用者向けサービスステータスページです。

Minecraftサーバー専用の運用画面ではなく、今後追加されるWeb、API、コミュニティ、ゲームなど複数サービスの稼働状況を同じ画面で公開できる構成にしています。

## 目的

- 利用者が「今使えるか」を最初の数秒で判断できる
- 現在の障害、メンテナンス、復旧状況を公開できる
- Minecraft以外のサービスを同じUIへ追加できる
- OCI上の既存JSONを維持しながらGitHubでUIを管理する
- `main`へのマージ後にGitHub ActionsからOCIへ安全にデプロイする

## データソース

将来の複数サービス対応では、次のAPIを優先して読み込みます。

```text
/api/status.json
```

スキーマは `docs/status-api-schema.md` を参照してください。

`/api/status.json` が存在しない間は、現在のcollectorが生成する次のAPIを自動変換して表示します。

```text
/api/current.json
/api/history.json
```

そのため、バックエンドを先に変更しなくても新しい利用者向けUIへ移行できます。

## ローカル確認

```bash
python3 -m http.server 4173
```

## 検証

```bash
python3 scripts/validate.py
node --check assets/app.js
bash -n scripts/deploy-oci.sh
bash -n scripts/rollback-oci.sh
```

## GitHub ActionsからOCIへデプロイ

`.github/workflows/deploy-oci.yml` は次の2経路に対応します。

1. `main`へのpush（通常はPRマージ後）
2. Actions画面からの手動実行

GitHub Environment `production` と、次のSecretsを設定します。

| Secret | 内容 |
|---|---|
| `OCI_HOST` | OCIインスタンスのホスト名またはIP |
| `OCI_USER` | 通常は `opc` |
| `OCI_SSH_KEY` | デプロイ専用Ed25519秘密鍵 |
| `OCI_KNOWN_HOSTS` | OCIホストのknown_hosts行 |

本番デプロイはUIファイルだけを更新し、collectorが生成する `/opt/ivrm/www/stats/api/` を保持します。

## OCIへ手動デプロイ

```bash
./scripts/deploy-oci.sh
```

既存UIは次へ退避されます。

```text
/opt/ivrm/www/stats.ui-backup-YYYYMMDD-HHMMSS
```

ロールバック：

```bash
./scripts/rollback-oci.sh /opt/ivrm/www/stats.ui-backup-YYYYMMDD-HHMMSS
```
