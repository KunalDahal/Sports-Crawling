# spcrawler

`spcrawler` is the Python crawl engine behind the full-stack app.

It searches sports-stream queries, builds a DFS graph of candidate pages, short-circuits known official domains, extracts page evidence, and classifies pages as `official`, `suspicious`, or `clean`.

## Current Behavior

1. Builds seven DDGS search queries from one match string
2. Collects up to 20 root results per keyword
3. Deduplicates nodes by canonical URL
4. Skips known official domains before page scraping
5. Crawls the remaining graph depth-first
6. Extracts title, text snippet, outbound links, iframes, and candidate stream URLs
7. Uses Gemini to classify the page and choose follow-up links
8. Falls back to local heuristics if Gemini fails
9. Stops after `MAX_DEPTH = 10` or `MAX_TOTAL_PAGES = 100`

Candidate stream URLs can come from:

- page HTML
- iframe sources
- discovered links
- captured network requests

## Source Layout

- `src/instance/scraper.py`: main crawl engine
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

This folder is source-based right now and does not include packaging metadata such as `pyproject.toml` or `setup.py`. Use it through the backend runner or import it from source.

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

- [src/instance/scraper.py](/W:/spcrawler/spcrawler/src/instance/scraper.py)
- [src/client/llm.py](/W:/spcrawler/spcrawler/src/client/llm.py)
- [src/client/model.py](/W:/spcrawler/spcrawler/src/client/model.py)
- [src/utils/constants.py](/W:/spcrawler/spcrawler/src/utils/constants.py)
