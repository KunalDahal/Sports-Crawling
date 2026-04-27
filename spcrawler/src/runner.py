from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .engine import EngineRequest, empty_state, run_request


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def main() -> None:
    request: EngineRequest | None = None
    try:
        raw = json.load(sys.stdin)
        request = EngineRequest.from_payload(raw)
        asyncio.run(run_request(request, emit))
    except Exception as exc:
        state = empty_state(request, status="failed", message="Runner failed")
        state["error"] = str(exc)
        emit(state)
        raise


if __name__ == "__main__":
    main()
