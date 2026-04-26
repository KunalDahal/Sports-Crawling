from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    api_key: str
    proxy_url: str = ""
