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
sudo install -d -m 0750 -o opc -g opc /opt/ivrm/compose/ivrm-status-api
sudo cp deploy/status-api/.env.example /opt/ivrm/compose/ivrm-status-api/.env
sudo chown opc:opc /opt/ivrm/compose/ivrm-status-api/.env
sudo chmod 600 /opt/ivrm/compose/ivrm-status-api/.env
sudo vi /opt/ivrm/compose/ivrm-status-api/.env
```

親ディレクトリもデプロイユーザーが参照できる必要があります。`root:root`かつ`0750`のままだと、`.env`自体が`opc:opc`でもGitHub Actionsから存在確認できません。

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

## Caddyfileの更新方式

本番Caddyfileはホストの単一ファイルを、コンテナの`/etc/caddy/Caddyfile`へbind mountしています。

```text
/opt/ivrm/compose/caddy/Caddyfile
  -> /etc/caddy/Caddyfile
```

この構成では、`install`や一時ファイルの`rename`でホスト側Caddyfileのinodeを置き換えると、起動中コンテナが古いinodeを参照し続ける場合があります。

デプロイスクリプトはCaddyfileを同じinodeへ上書きし、次を検証してからreloadします。

- ホスト側とコンテナ側のCaddyfileが同一内容
- Status APIのmatcherとupstreamがadapt後のJSONへ存在
- `caddy validate`が成功

過去のデプロイでCaddyfileのinodeがすでに置き換わっており、起動中コンテナが古いinodeを参照している場合は、同一inodeへの上書きだけでは復旧できません。

その場合、スクリプトは次を行います。

1. ホスト側とコンテナ側のSHA-256不一致を検出
2. CaddyコンテナのCompose作業ディレクトリとサービス名をラベルから取得
3. `docker compose up -d --no-deps --force-recreate`でCaddyだけを一度再作成
4. bind mountが現在のホストCaddyfileへ付け直されたことを再検証
5. validateとreloadを続行

Caddyの再作成中は、数秒程度HTTPS接続が切れる可能性があります。この自動復旧は、ホスト側とコンテナ側の内容が一致しない場合だけ実行されます。

手動確認：

```bash
sudo sha256sum /opt/ivrm/compose/caddy/Caddyfile
docker exec caddy sha256sum /etc/caddy/Caddyfile
```

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

戻す場合も、単一ファイルbind mountのinodeを維持するため、`cp`や`install`ではなく内容を上書きします。

```bash
BACKUP=<backup>
CADDYFILE=/opt/ivrm/compose/caddy/Caddyfile
sudo sh -c 'cat "$1" > "$2"' sh "$BACKUP" "$CADDYFILE"
sudo chmod 0644 "$CADDYFILE"

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
