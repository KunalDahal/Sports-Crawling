# backend

Go API wrapper for the Python `spcrawler` engine.

## Run

```powershell
cd D:\spcrawler\backend
go run .\cmd\server
```

The server listens on `http://localhost:8080` by default.

## API

- `POST /api/sessions` starts a scraper process.
- `GET /api/sessions` lists sessions.
- `GET /api/sessions/{id}` returns one session summary.
- `GET /api/sessions/{id}/events` streams crawler events with Server-Sent Events.
- `DELETE /api/sessions/{id}` stops a running session.

Request body:

```json
{
  "keyword": "MI Vs GT",
  "api_key": "gemini-key",
  "db_name": "sports_scraper",
  "mongo_uri": "mongodb://localhost:27017",
  "proxy_url": ""
}
```

The backend does not modify `spcrawler`; it launches `backend/scripts/run_scraper.py`,
which creates a `Scraper` instance and forwards the engine's native events as JSON.
