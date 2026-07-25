# OCI Status APIデプロイ

## 構成

```text
Lightsail status-agent
  -> HTTPS + HMAC
Caddy (stats.ivrm.jp)
  -> ivrm-status-api:8080
SQLite (/opt/ivrm/compose/ivrm-status-api/data/status.db)
  + Minecraft JSON read-only mount
```

## 初回のみ必要な設定

OCIでSecretファイルを作成します。

```bash
sudo install -d -m 0750 /opt/ivrm/compose/ivrm-status-api
sudo cp deploy/status-api/.env.example /opt/ivrm/compose/ivrm-status-api/.env
sudo chown opc:opc /opt/ivrm/compose/ivrm-status-api/.env
sudo chmod 600 /opt/ivrm/compose/ivrm-status-api/.env
sudo vi /opt/ivrm/compose/ivrm-status-api/.env
```

`HERTA_INGEST_SECRET` は32文字以上のランダム値を設定します。Herta status-agent側にも同じ値を安全に登録します。

生成例：

```bash
openssl rand -hex 32
```

GitHub Environment `production` では既存UIと同じ次のSecretsを利用します。

- `OCI_HOST`
- `OCI_USER`
- `OCI_SSH_KEY`
- `OCI_KNOWN_HOSTS`

GHCRのpush・一時pull認証には同一リポジトリの`GITHUB_TOKEN`を利用し、デプロイ終了時にOCIからlogoutします。

## 自動デプロイ

`main`へ対象ファイルがマージされると、`Deploy Status API to OCI`が次を実行します。

1. pytest
2. linux/arm64イメージをBuildxで作成
3. GHCRへSHAタグとlatestタグをpush
4. OCIへデプロイ資材をSCP
5. OCIでGHCRへ一時ログイン
6. `docker compose pull`
7. `docker compose up -d --no-build`
8. Caddy設定をバックアップ・検証・reload
9. 公開APIのスモークテスト
10. OCIでGHCRからlogout

OCI上でローカルbuildは行いません。

## 確認

```bash
docker ps --filter name=ivrm-status-api
docker logs --tail 100 ivrm-status-api
curl -fsS https://stats.ivrm.jp/api/status.json | jq
```

## Caddyバックアップ

自動設定前のCaddyfileは次へ保存されます。

```text
/opt/ivrm/compose/caddy/Caddyfile.status-api-backup-YYYYMMDD-HHMMSS
```

戻す場合：

```bash
sudo cp -a <backup> /opt/ivrm/compose/caddy/Caddyfile
CADDY_CONTAINER=$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /^caddy(:|@)/ {print $1; exit}')
docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
```

## SQLiteバックアップ

本番導入後は、WALを考慮してSQLite backup APIまたはコンテナ停止を伴わない整合性あるバックアップを別途追加します。単純な稼働中ファイルコピーは避けます。

## 自動デプロイの有効化

初回設定と手動デプロイが成功した後、GitHub Repository Variableを設定します。

```text
STATUS_API_AUTO_DEPLOY=true
```

設定前は`main`へマージしてもStatus APIの本番jobはskipされます。UIデプロイには影響しません。
