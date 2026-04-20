from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SPCRAWLER_DIR = ROOT / "spcrawler"
sys.path.insert(0, str(SPCRAWLER_DIR))

from src import Scraper  # noqa: E402
from src.events import Event  # noqa: E402


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


async def main() -> None:
    req = json.load(sys.stdin)
    scraper = Scraper(
        keyword=req.get("keyword", ""),
        api_key=req.get("api_key", ""),
        db_name=req.get("db_name", "spcrawler"),
        mongo_uri=req.get("mongo_uri", "mongodb://localhost:27017"),
        proxy_url=req.get("proxy_url", ""),
    )

    async def on_event(event: Event) -> None:
        emit(event.as_dict())

    scraper.subscribe(on_event)

    try:
        streams = await scraper.run()
        emit(
            {
                "type": "runner.finished",
                "session_id": scraper.session_id,
                "data": {"streams": streams, "count": len(streams)},
            }
        )
    except Exception as exc:
        emit(
            {
                "type": "runner.error",
                "session_id": scraper.session_id,
                "data": {"context": "scraper_run", "error": str(exc)},
            }
        )
        raise


if __name__ == "__main__":
    asyncio.run(main())
