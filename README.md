# spcrawler

spcrawler is a full-stack sports stream investigation workspace.

It combines:
- a Python crawler that searches sports stream queries with DDGS
- a Go backend that manages crawler sessions and streams live snapshots
- a React frontend that shows the crawl as a live graph with node inspection

## What It Does

1. Accepts one match string such as `CSK vs GT IPL 2026`
2. Builds DDGS search queries from that match
3. Creates root nodes from search results
4. Marks obvious official domains immediately from hostname hints
5. Crawls suspicious pages with DFS
6. Sends match context, search keyword, page snippet, iframes, and links to the LLM
7. Lets the LLM classify the page as `official`, `suspicious`, or `clean`
8. Lets the LLM choose which child links should be visited next
9. Streams live state updates to the UI

## Current Behavior

- Official broadcaster and league domains such as Hotstar, JioCinema, ESPN, IPLT20, ICC, and similar known hosts are short-circuited before scraping.
- Only suspicious pages expand into child nodes.
- Child nodes are deduplicated with canonical URLs, and self-links are filtered out.
- Each child is crawled from its own page URL, not from reused parent page content.
- The live UI shows a short status trail such as scraping, LLM check, classification done, and child expansion.

## Stack

- Frontend: React + Vite
- Backend: Go with `net/http` and SSE
- Crawler: Python with `crawl4ai`, `ddgs`, and `requests`
- LLM: Gemini API

## Prerequisites

- Node.js 18+
- npm 9+
- Go 1.22+
- Python 3.11+
- Gemini API key

## Quick Start

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

This starts:
- backend API
- frontend dev server

If the default ports are busy, `start.ps1` chooses the next free ones and prints them.

## Manual Start

Backend:

```powershell
cd backend
go run .\cmd\server
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Crawler dependencies:

```powershell
cd backend\scripts
pip install -r requirements.txt
```

Then run the browser setup for `crawl4ai` once in the Python environment:

```powershell
crawl4ai-setup
```

## Session Request

`POST /api/sessions`

```json
{
  "match": "CSK vs GT IPL 2026",
  "api_key": "gemini-key",
  "proxy_url": ""
}
```

## Main API

- `POST /api/sessions` starts a session
- `GET /api/sessions` lists session summaries
- `GET /api/sessions/{id}` returns one summary
- `GET /api/sessions/{id}/state` returns the latest full snapshot
- `GET /api/sessions/{id}/stream` streams live snapshots with SSE
- `DELETE /api/sessions/{id}` stops a running session
- `POST /api/sessions/{id}/remove` removes the session from memory

## Repo Layout

```text
spcrawler/
|-- README.md
|-- start.ps1
|-- backend/
|   |-- README.md
|   |-- cmd/server/main.go
|   |-- internal/sessions/
|   |   |-- http.go
|   |   `-- manager.go
|   `-- scripts/
|       |-- requirements.txt
|       `-- run_scraper.py
|-- frontend/
|   |-- index.html
|   |-- package.json
|   |-- scripts/graph-logic-check.mjs
|   `-- src/
|       |-- graph-logic.js
|       |-- main.jsx
|       `-- styles.css
`-- spcrawler/
    |-- README.MD
    `-- src/
        |-- __init__.py
        |-- client/
        |   |-- llm.py
        |   |-- model.py
        |   `-- prompts.py
        |-- instance/
        |   |-- proxy_manager.py
        |   `-- scraper.py
        `-- utils/
            |-- config.py
            `-- constants.py
```

## Docs

- [backend/README.md](/w:/spcrawler/backend/README.md)
- [spcrawler/README.MD](/w:/spcrawler/spcrawler/README.MD)
