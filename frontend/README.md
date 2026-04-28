# frontend

React control room for live `spcrawler` sessions.

## What The UI Does

- starts a crawl with `match` and `api_key`
- lists recent in-memory sessions from the backend
- subscribes to live state updates over SSE
- renders the crawl as a zoomable DFS graph
- shows live counters for keywords, roots, visited pages, and verdict totals
- lets you inspect node details, stream URLs, iframes, and extracted links
- lets you stop or remove a session

## Run

```powershell
cd frontend
npm install
npm run dev
```

The app defaults to `http://localhost:8080`.

To point it at a different backend:

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8090"
npm run dev
```

In production Docker and Heroku deployments, the built frontend is served by the Go backend from the same origin, so `VITE_API_BASE` is not needed there.

## Build

```powershell
cd frontend
npm run build
npm run preview
```

The root Docker image runs this build automatically and copies the generated `dist` folder into the runtime image.

## Session Flow

1. Submit a match string and Gemini API key.
2. The frontend sends `POST /api/sessions`.
3. It fetches `GET /api/sessions/{id}/state` for the initial snapshot.
4. It listens to `GET /api/sessions/{id}/stream` for live SSE updates.
5. Each page node is rendered under the session root and colored by verdict.

Color meanings:

- blue: `official`
- red: `suspicious`
- green: `clean`
- yellow: pending or unclassified
- gray: error or stopped state

## Main Files

- [package.json](package.json)
- [src/main.jsx](src/main.jsx)
- [src/graph-logic.js](src/graph-logic.js)
- [src/styles.css](src/styles.css)
