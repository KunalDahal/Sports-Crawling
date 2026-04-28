from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from .instance.scraper import Scraper

UpdateCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class EngineRequest:
    description: str
    api_key: str = ""
    proxy_url: str = ""
    session_id: str = ""
    link: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EngineRequest":
        description = str(payload.get("description") or payload.get("match") or payload.get("keyword") or "").strip()
        link = str(payload.get("link") or "").strip()
        if not description and link:
            description = link
        return cls(
            description=description,
            api_key=str(payload.get("api_key") or "").strip(),
            proxy_url=str(payload.get("proxy_url") or "").strip(),
            session_id=str(payload.get("session_id") or "").strip(),
            link=link,
        )


def empty_state(request: EngineRequest | None = None, *, status: str = "failed", message: str = "") -> dict[str, Any]:
    return {
        "session_id": request.session_id if request else "",
        "match": request.description if request else "",
        "status": status,
        "message": message,
        "error": "",
        "started_at": "",
        "finished_at": "",
        "current_node_id": "",
        "current_url": "",
        "active_keyword_id": "",
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


async def run_request(request: EngineRequest, on_update: UpdateCallback | None = None) -> dict[str, Any]:
    scraper = Scraper(
        match=request.description,
        link=request.link,
        api_key=request.api_key,
        proxy_url=request.proxy_url,
        session_id=request.session_id,
        on_update=on_update,
    )
    return await scraper.run()


def run_request_sync(request: EngineRequest, on_update: UpdateCallback | None = None) -> dict[str, Any]:
    return asyncio.run(run_request(request, on_update))
