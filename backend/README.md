# backend

Go session manager for the Python `spcrawler` crawler.

## What It Does

- starts Python crawler sessions
- keeps the latest state snapshot for each session
- exposes session APIs
- streams live snapshots to the frontend over SSE

The backend is intentionally thin. Most crawl logic lives in the Python package.

## Run

```powershell
cd W:\spcrawler\backend
go run .\cmd\server
```

Default address:

```text
http://localhost:8080
```

## Session API

- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `GET /api/sessions/{id}/state`
- `GET /api/sessions/{id}/stream`
- `DELETE /api/sessions/{id}`
- `POST /api/sessions/{id}/remove`

## Start Request

```json
{
  "match": "CSK vs GT IPL 2026",
  "api_key": "gemini-key",
  "proxy_url": ""
}
```

## Runtime Notes

- The backend launches `backend/scripts/run_scraper.py`.
- The Python runner emits full JSON snapshots on stdout.
- The backend stores the newest snapshot and forwards it to SSE subscribers.
- Sessions can be stopped or removed without restarting the server.

## Environment

- `ADDR` sets the listen address. Default: `:8080`

## Related Files

- [cmd/server/main.go](/w:/spcrawler/backend/cmd/server/main.go)
- [internal/sessions/http.go](/w:/spcrawler/backend/internal/sessions/http.go)
- [internal/sessions/manager.go](/w:/spcrawler/backend/internal/sessions/manager.go)
- [scripts/run_scraper.py](/w:/spcrawler/backend/scripts/run_scraper.py)
