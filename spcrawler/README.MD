# spcrawler

`spcrawler` is the Python crawl engine behind the full-stack app.

It turns a match description into a single search keyword, filters search results down to suspicious candidate pages, builds a DFS graph, short-circuits known official domains, extracts page evidence, and classifies pages as `official`, `suspicious`, or `clean`.

## Current Behavior

1. Uses Gemini to summarize the user's match description into one DDGS search keyword
2. Collects DDGS results for that keyword
3. Uses Gemini to skip official pages, news, blogs, score pages, and generic sports content before root nodes are created
4. Deduplicates suspicious root nodes by canonical URL
5. Skips known official domains before page scraping
6. Crawls the remaining graph depth-first
7. Extracts title, text snippet, up to 100 outbound links, iframes, and up to 5 candidate stream URLs
8. Uses Gemini to classify each page and choose suspicious follow-up links
9. Falls back to local heuristics if Gemini fails
10. Stops after `MAX_DEPTH = 10` or `MAX_TOTAL_PAGES = 100`

In the single-container runtime, the backend launches the Python runner from the same image and serves the built frontend from the same origin.

Candidate stream URLs can come from:

- page HTML
- iframe sources
- discovered links
- captured network requests

## Source Layout

- `src/instance/scraper.py`: workflow orchestrator and single-URL `SPCrawler`
- `src/client/model.py`: Gemini HTTP client
- `src/client/llm.py`: prompt shaping, parsing, and fallback heuristics
- `src/client/prompts.py`: classification prompts
- `src/utils/constants.py`: limits, search templates, and official domain hints

## Requirements

- Python 3.8+
- `crawl4ai`
- `ddgs`
- `requests`
- A Gemini API key for best results

Install the runtime dependencies:

```powershell
cd W:\spcrawler\backend\scripts
python -m pip install -r requirements.txt
```

Then run `crawl4ai-setup` once in that Python environment if browser binaries are not installed yet.

## Usage

This folder is a Python package. The backend installs it into its scraper venv in editable mode and starts one Python process per scraper session. The production Docker image also installs it into the runtime image so the backend can invoke the runner without a separate crawler container.

Install the engine package manually when needed:

```powershell
cd W:\spcrawler\spcrawler
python -m pip install -e .
```

The engine runner accepts JSON on stdin with:

- `description`: match/event text used by the LLM to generate keywords
- `api_key`: Gemini API key
- `proxy_url`: optional proxy URL
- `session_id`: backend session id

Use it through the backend runner or import it from source.

If you want to run it directly, execute from `W:\spcrawler\spcrawler` or add that folder to `PYTHONPATH`, then import from `src`:

```python
import asyncio
from src import Scraper


def show(state: dict) -> None:
    print(state["status"], state["message"])


async def main() -> None:
    scraper = Scraper(
        match="CSK vs GT IPL 2026",
        api_key="your_gemini_key",
        proxy_url="",
        on_update=show,
    )
    final_state = await scraper.run()
    print(final_state["stats"])


asyncio.run(main())
```

For dedicated crawling, pass a single URL either as `link` or as the `match` value:

```python
from src import SPCrawler

crawler = SPCrawler(
    link="https://example.com/player",
    api_key="your_gemini_key",
    proxy_url="",
)
```

## Snapshot Shape

Each snapshot contains:

- `session_id`
- `match`
- `status`
- `message`
- `error`
- `started_at`
- `finished_at`
- `current_node_id`
- `current_url`
- `keywords`
- `nodes`
- `stats`

Each node includes:

- `id`
- `parent_id`
- `keyword_id`
- `root`
- `depth`
- `url`
- `title`
- `summary`
- `links`
- `iframes`
- `stream_urls`
- `child_ids`
- `classification`
- `color`
- `reason`
- `status`
- `visited`

## Related Files

- [src/instance/scraper.py](src/instance/scraper.py)
- [src/client/llm.py](src/client/llm.py)
- [src/client/model.py](src/client/model.py)
- [src/utils/constants.py](src/utils/constants.py)
