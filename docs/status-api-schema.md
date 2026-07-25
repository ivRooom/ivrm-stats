# Public Status API schema

Minecraft以外のサービスを追加するための公開ステータスAPIです。

## Endpoint

```text
GET /api/status.json
```

## Example

```json
{
  "generated_at": "2026-07-25T01:30:00+00:00",
  "overall_status": "operational",
  "message": "すべてのサービスは正常に稼働しています。",
  "services": [
    {
      "id": "minecraft-network",
      "group": "ゲームサービス",
      "name": "Minecraft Network",
      "description": "GT New Horizons",
      "status": "operational",
      "timeline": ["operational", "operational"],
      "meta": {
        "type": "minecraft",
        "connection": "mc.ivrm.jp",
        "playersOnline": 0,
        "playersMax": 5,
        "mode": "GTNH 2.8.4 / GregTech Expert"
      }
    },
    {
      "id": "public-website",
      "group": "Webサービス",
      "name": "ivrm.jp",
      "description": "ivRooom公式Webサイト",
      "status": "operational",
      "timeline": ["operational", "operational"]
    }
  ],
  "incidents": [
    {
      "id": "incident-20260725-01",
      "title": "API応答遅延",
      "status": "resolved",
      "impact": "minor",
      "message": "API応答遅延は解消しました。",
      "started_at": "2026-07-25T00:10:00+00:00",
      "updated_at": "2026-07-25T00:35:00+00:00"
    }
  ]
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

`timeline` は古い順に最大24件を推奨します。24件未満の場合、フロントエンドは不足分を `unknown` として補完します。
