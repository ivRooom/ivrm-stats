# Public Status API schema

Minecraft、Herta、将来のWeb・APIサービスを同じ形式で公開するステータスAPIです。

## Endpoint

```text
GET /api/status.json
```

## Response example

```json
{
  "generated_at": "2026-07-25T12:30:00+00:00",
  "overall_status": "operational",
  "services": [
    {
      "id": "minecraft-network",
      "group": "ゲームサービス",
      "name": "Minecraft Network",
      "description": "GT New Horizons",
      "status": "operational",
      "checked_at": "2026-07-25T12:29:30+00:00",
      "last_received_at": "2026-07-25T12:29:30+00:00",
      "timeline": ["unknown", "operational"],
      "meta": {
        "type": "minecraft",
        "connection": "mc.ivrm.jp",
        "playersOnline": 0,
        "playersMax": 5,
        "mode": "GTNH 2.8.4"
      }
    },
    {
      "id": "herta-discord-bot",
      "group": "Discordサービス",
      "name": "Herta",
      "description": "ivRooom Discord Bot",
      "status": "operational",
      "checked_at": "2026-07-25T12:29:45+00:00",
      "last_received_at": "2026-07-25T12:29:46+00:00",
      "timeline": ["unknown", "operational"],
      "meta": {
        "type": "discord_bot",
        "version": "0.1.0"
      }
    }
  ],
  "incidents": []
}
```

## Status values

```text
operational
maintenance
degraded
outage
unknown
```

全体状態と時間帯の状態は、次の優先順位で最も悪い値を採用します。

```text
operational < maintenance < degraded < outage < unknown
```

## Timeline

`timeline`は24時間を1時間単位で古い順に返します。同じ時間帯に複数の記録がある場合は最も悪い状態を採用し、データがない時間帯は`unknown`です。

## Stale

- Herta: 最終受信から120秒を超えると`unknown`
- Minecraft: collectorの更新時刻が既定300秒を超えると`unknown`

stale判定は公開APIを呼び出すたびに評価します。

## 公開しない情報

- Hertaの内部`checks`
- PostgreSQL・Redis・Workerの個別状態
- AWS Lightsail・OCIの内部情報
- 内部IP、DB接続情報、環境変数
- HMAC署名、共有鍵、request ID
- スタックトレースや内部エラー全文
