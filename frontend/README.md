# frontend

React control room for live `spcrawler` sessions.

## Run

```powershell
cd D:\spcrawler\frontend
npm install
npm run dev
```

By default the app calls `http://localhost:8080`. Override with:

```powershell
$env:VITE_API_BASE="http://localhost:8080"
npm run dev
```

## Flow

1. Submit keyword, API key, Mongo database, Mongo URI, and optional proxy URL.
2. The Go backend starts one Python scraper runner for that session.
3. The UI subscribes to `/api/sessions/{id}/events`.
4. Each crawler event becomes or updates a node in the live session graph.
