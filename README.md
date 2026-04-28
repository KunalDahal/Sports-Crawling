# spcrawler

`spcrawler` is a sports-stream investigation workspace with three parts:

- `frontend`: a React/Vite UI for starting sessions and inspecting the live graph
- `backend`: a Go API that manages sessions and streams state updates over SSE
- `spcrawler`: the Python crawl engine that searches, crawls, classifies, and expands suspicious pages

## What It Does

1. Accepts a match string such as `CSK vs GT IPL 2026`
2. Uses Gemini to summarize that description into one DDGS search keyword
3. Uses DDGS to return multiple links for that keyword
4. Uses Gemini to skip official pages, news articles, blogs, score pages, and generic sports content before root nodes are created
5. Crawls only suspicious root pages with DFS
6. Extracts summaries, up to 100 outbound links, iframes, and up to 5 candidate stream URLs
7. Uses Gemini to classify each page as `official`, `suspicious`, or `clean`
8. Lets the model choose which suspicious child links should be explored next
9. Streams full state snapshots to the frontend

If Gemini calls fail, the crawler falls back to local heuristics so a session can still complete.

## Stack

- Frontend: React 19 + Vite 7
- Backend: Go 1.22 + `net/http`
- Crawler: Python + `crawl4ai` + `ddgs` + `requests`
- Streaming: Server-Sent Events
- LLM: Google Gemini `gemini-2.5-flash-lite`

## Prerequisites

- Node.js 18+
- npm
- Go 1.22+
- Python 3.8+
- Internet access for DDGS, page crawling, and Gemini requests
- A Gemini API key for best classification quality

## Quick Start

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The launcher:

- picks the first free backend port starting at `8080`
- picks the first free frontend port starting at `5173`
- opens backend and frontend in separate PowerShell windows
- sets `VITE_API_BASE` automatically for the frontend

The script prints the exact frontend and backend URLs it started.

## Manual Start

Backend:

```powershell
cd W:\spcrawler\backend
go run .\cmd\server
```

Frontend:

```powershell
cd W:\spcrawler\frontend
npm install
npm run dev
```

The backend creates `backend\scripts\.venv` and installs `backend\scripts\requirements.txt` the first time you start a crawl. If `crawl4ai` browser binaries are missing, open that venv and run `crawl4ai-setup` once.

## Docker Run

Build and run the full stack from the repository root:

```powershell
docker compose up -d --build
```

The frontend is exposed on port `80` and proxies API/SSE traffic to the backend internally.

Useful commands:

```powershell
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

## Deploy To DigitalOcean (Droplet)

1. Create a Droplet (Ubuntu 22.04+ recommended) with ports `22`, `80`, and `443` allowed.
2. SSH into the Droplet.
3. Install Docker Engine + Compose plugin.
4. Clone this repository.
5. Run:

```bash
docker compose up -d --build
```

6. Visit `http://<droplet-ip>`.

For a complete production checklist and hardened setup commands, see [DEPLOY_DIGITALOCEAN.md](DEPLOY_DIGITALOCEAN.md).

## Session API

Start request:

```json
{
  "match": "CSK vs GT IPL 2026",
  "api_key": "your-gemini-key",
  "proxy_url": ""
}
```

Main routes:

- `GET /api/health`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `GET /api/sessions/{id}/state`
- `GET /api/sessions/{id}/stream`
- `GET /api/sessions/{id}/events` alias for the same SSE stream
- `DELETE /api/sessions/{id}`
- `POST /api/sessions/{id}/remove`

Each streamed event is emitted as SSE `event: state` with the full session snapshot.

## Repo Layout

```text
spcrawler/
|-- README.md
|-- start.ps1
|-- backend/
|   |-- README.md
|   |-- cmd/server/main.go
|   |-- internal/sessions/
|   `-- scripts/
|-- frontend/
|   |-- README.md
|   |-- package.json
|   `-- src/
`-- spcrawler/
    |-- README.MD
    `-- src/
```

## Notes

- The UI uses `/api/sessions/{id}/stream`.
- The backend also accepts `/api/sessions/{id}/events` for compatibility.
- Official domains are short-circuited before page scraping.
- Suspicious pages can expose direct stream URLs from page HTML, iframes, discovered links, or captured network requests.

## Docs

- [backend/README.md](/W:/spcrawler/backend/README.md)
- [frontend/README.md](/W:/spcrawler/frontend/README.md)
- [spcrawler/README.MD](/W:/spcrawler/spcrawler/README.MD)
