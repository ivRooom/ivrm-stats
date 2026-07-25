# ivRooom Status API

FastAPI・SQLiteで構成する、`stats.ivrm.jp`のステータス受信・統合APIです。

## API

- `POST /api/internal/status-ingest`: HMAC署名付き内部受信
- `GET /api/status.json`: MinecraftとHertaの公開状態
- `GET /healthz`: APIとSQLiteの疎通確認

## ローカル実行

```bash
cd services/status-api
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export STATUS_DB_PATH=/tmp/ivrm-status.db
export HERTA_INGEST_SECRET=local-development-secret-32-characters
export MINECRAFT_CURRENT_PATH=/tmp/current.json
export MINECRAFT_HISTORY_PATH=/tmp/history.json
uvicorn app.main:app --reload --port 8080
```

## テスト

```bash
pytest
```

## 設計上の境界

Hertaの内部`checks`は受信せず、公開に必要なservice metadata、status、checked_at、version、summaryだけを保存します。DB、Redis、AWS、Discord Guild、内部IP、スタックトレースは公開APIへ含めません。
