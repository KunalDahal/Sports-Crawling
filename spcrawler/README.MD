# spcrawler

`spcrawler` is the Python crawl engine used by the full-stack app.

It searches sports-stream queries, builds a DFS graph of candidate pages, marks official domains early, and asks the LLM both how to classify a page and which child links to explore next.

## Flow

1. Take one match such as `CSK vs GT IPL 2026`
2. Build DDGS search queries from the match
3. Search each query with DDGS
4. Create root nodes from the results
5. Detect known official domains from hostname and skip scraping them
6. Visit non-official nodes with DFS
7. Extract that page's own summary, links, and iframes
8. Send match + search keyword + page context to the LLM
9. Classify the page as `official`, `suspicious`, or `clean`
10. If suspicious, follow only the child links selected by the LLM
11. Never revisit the same canonical URL twice

## Labels

- `official` -> blue
- `suspicious` -> red
- `clean` -> green

## Notes

- Official domains such as Hotstar, JioCinema, ESPN, IPLT20, ICC, and similar known hosts can be resolved from domain name alone.
- Child nodes are created only for genuinely different URLs after canonical dedupe and self-link filtering.
- Child summaries and links come from the child page itself.

## Install

```bash
git clone https://github.com/KunalDahal/spcrawler.git
cd spcrawler
pip install -e .
```

Then run browser setup for `crawl4ai`:

```bash
crawl4ai-setup
```

## Usage

```python
import asyncio
from spcrawler import Scraper


def show(state: dict) -> None:
    print(state["status"], state["message"])


async def main():
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

`run()` returns the final state snapshot.

## Snapshot Shape

Each snapshot contains:

- `session_id`
- `match`
- `status`
- `message`
- `error`
- `current_node_id`
- `current_url`
- `keywords`
- `nodes`
- `stats`

Each node includes:

- parent id
- keyword id
- depth
- url
- title
- summary
- links
- iframes
- child ids
- classification
- color
- reason
- status
- visited

## Dependencies

- [crawl4ai](https://github.com/unclecode/crawl4ai)
- [ddgs](https://pypi.org/project/ddgs/)
- [requests](https://pypi.org/project/requests/)

## License

MIT
