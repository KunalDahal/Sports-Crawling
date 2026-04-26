from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPCRAWLER_DIR = ROOT / "spcrawler"
sys.path.insert(0, str(SPCRAWLER_DIR))

from src import Scraper


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


async def main() -> None:
    req = json.load(sys.stdin)
    match = req.get("match", "") or req.get("keyword", "")

    scraper = Scraper(
        match=match,
        api_key=req.get("api_key", ""),
        proxy_url=req.get("proxy_url", ""),
        session_id=req.get("session_id", ""),
        on_update=emit,
    )
    await scraper.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        emit(
            {
                "session_id": "",
                "match": "",
                "status": "failed",
                "message": "Runner failed",
                "error": str(exc),
                "started_at": "",
                "finished_at": "",
                "current_node_id": "",
                "current_url": "",
                "keywords": [],
                "nodes": [],
                "stats": {
                    "keywords": 0,
                    "roots": 0,
                    "visited": 0,
                    "official": 0,
                    "suspicious": 0,
                    "clean": 0,
                },
            }
        )
        raise
