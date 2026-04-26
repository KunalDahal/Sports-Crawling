from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from . import prompts
from .model import Model
from ..utils.constants import LLM_MAX_REQUEST_CHARS, OFFICIAL_DOMAIN_HINTS

_MATCH_LIMIT = 120
_URL_LIMIT = 220
_TITLE_LIMIT = 120
_SNIPPET_LIMIT = 320
_ERROR_LIMIT = 180
_IFRAME_LIMIT = 160
_LINK_TITLE_LIMIT = 40
_LINK_URL_LIMIT = 160
_MAX_NEXT_LINKS = 6
_SUSPICIOUS_RE = re.compile(
    r"(stream|player|embed|m3u8|hls|telegram|mirror|redirect|acestream|streaming|crichd|streameast|buffstream|cricfree|sportsurge)",
    re.IGNORECASE,
)


def _clip(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 2)].rstrip()}.."


def _make_links(raw_links: list[dict], *, count: int) -> str:
    links = [
        {
            "title": _clip(link.get("title", ""), _LINK_TITLE_LIMIT),
            "url": _clip(link.get("url", ""), _LINK_URL_LIMIT),
        }
        for link in raw_links[:count]
    ]
    return json.dumps(links, ensure_ascii=True, separators=(",", ":"))


def _make_iframes(raw_iframes: list[str], *, count: int) -> str:
    iframes = [_clip(url, _IFRAME_LIMIT) for url in raw_iframes[:count]]
    return json.dumps(iframes, ensure_ascii=True, separators=(",", ":"))


def _collect_urls(raw: object, allowed: set[str] | None = None) -> list[str]:
    urls: list[str] = []
    if not isinstance(raw, list):
        return urls
    for value in raw:
        url = str(value or "").strip()
        if not url:
            continue
        if allowed is not None and url not in allowed:
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= _MAX_NEXT_LINKS:
            break
    return urls


def _looks_suspicious(*values: object) -> bool:
    return any(_SUSPICIOUS_RE.search(str(value or "")) for value in values)


def _official_domain_hint(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    for hint in OFFICIAL_DOMAIN_HINTS:
        normalized = hint.lower().strip(".")
        if host == normalized or host.endswith(f".{normalized}"):
            return normalized
    return ""


def _fallback_next_links(raw_links: list[dict]) -> list[str]:
    picks: list[str] = []
    for link in raw_links:
        url = str(link.get("url", "")).strip()
        title = str(link.get("title", "")).strip()
        if not url:
            continue
        if _looks_suspicious(url, title) and url not in picks:
            picks.append(url)
        if len(picks) >= _MAX_NEXT_LINKS:
            break
    return picks


def _fallback_node_verdict(page_data: dict) -> dict:
    url = page_data.get("url", "")
    title = page_data.get("title", "")
    snippet = page_data.get("text_snippet", "")
    iframes = page_data.get("iframes", [])
    links = page_data.get("links_found", [])
    official_hint = _official_domain_hint(url)
    if official_hint:
        return {"label": "official", "reason": f"official domain {official_hint}", "next_links": []}
    suspicious_links = _fallback_next_links(links)
    if _looks_suspicious(url, title, snippet, " ".join(iframes)):
        return {
            "label": "suspicious",
            "reason": "stream-style page",
            "next_links": suspicious_links,
        }
    if suspicious_links:
        return {
            "label": "suspicious",
            "reason": "suspicious child links",
            "next_links": suspicious_links,
        }
    return {"label": "clean", "reason": "", "next_links": []}


def _fallback_error_verdict(error_data: dict) -> dict:
    official_hint = _official_domain_hint(error_data.get("url", ""))
    if official_hint:
        return {"label": "official", "reason": f"official domain {official_hint}", "next_links": []}
    if _looks_suspicious(
        error_data.get("url", ""),
        error_data.get("title", ""),
        error_data.get("snippet", ""),
        error_data.get("error", ""),
    ):
        return {"label": "suspicious", "reason": "stream-style failed page", "next_links": []}
    return {"label": "clean", "reason": "", "next_links": []}


class LLM:
    def __init__(self, model: Model) -> None:
        self._model = model

    def _parse_label(self, raw: str) -> dict:
        clean = re.sub(r"```[a-z]*|```", "", raw).strip()
        data = json.loads(clean)
        label = str(data.get("label", "")).lower().strip()
        if label not in {"official", "suspicious", "clean"}:
            label = "clean"
        return {
            "label": label,
            "reason": str(data.get("reason", "")).strip(),
            "next_links": _collect_urls(data.get("next_links")),
        }

    def classify_node(self, match: str, keyword: str, page_data: dict) -> dict:
        match_text = _clip(match, _MATCH_LIMIT)
        keyword_text = _clip(keyword, _MATCH_LIMIT)
        url_text = _clip(page_data.get("url", ""), _URL_LIMIT)
        title_text = _clip(page_data.get("title", ""), _TITLE_LIMIT)
        snippet_text = _clip(page_data.get("text_snippet", ""), _SNIPPET_LIMIT)
        raw_links = page_data.get("links_found", [])
        raw_iframes = page_data.get("iframes", [])
        allowed_urls = {str(link.get("url", "")).strip() for link in raw_links if str(link.get("url", "")).strip()}
        payload = prompts.CLASSIFY_NODE_USER.format(
            match=match_text,
            keyword=keyword_text,
            url=url_text,
            title=title_text,
            snippet=snippet_text,
            iframes=_make_iframes(raw_iframes, count=6),
            links=_make_links(raw_links, count=8),
        )
        if len(prompts.CLASSIFY_NODE_SYSTEM) + len(payload) > LLM_MAX_REQUEST_CHARS:
            payload = prompts.CLASSIFY_NODE_USER.format(
                match=match_text,
                keyword=keyword_text,
                url=url_text,
                title=title_text,
                snippet=_clip(snippet_text, 180),
                iframes=_make_iframes(raw_iframes, count=3),
                links=_make_links(raw_links, count=4),
            )
        if len(prompts.CLASSIFY_NODE_SYSTEM) + len(payload) > LLM_MAX_REQUEST_CHARS:
            payload = prompts.CLASSIFY_NODE_USER.format(
                match=match_text,
                keyword=keyword_text,
                url=url_text,
                title=title_text,
                snippet=_clip(snippet_text, 96),
                iframes="[]",
                links="[]",
            )
        try:
            raw = self._model.call(prompts.CLASSIFY_NODE_SYSTEM, payload, operation="classify_node")
            verdict = self._parse_label(raw)
            verdict["next_links"] = _collect_urls(verdict.get("next_links"), allowed_urls)
            if verdict["label"] != "suspicious":
                verdict["next_links"] = []
            return verdict
        except Exception:
            return _fallback_node_verdict(page_data)

    def classify_error(self, match: str, keyword: str, error_data: dict) -> dict:
        payload = prompts.CLASSIFY_ERROR_USER.format(
            match=_clip(match, _MATCH_LIMIT),
            keyword=_clip(keyword, _MATCH_LIMIT),
            url=_clip(error_data.get("url", ""), _URL_LIMIT),
            title=_clip(error_data.get("title", ""), _TITLE_LIMIT),
            snippet=_clip(error_data.get("snippet", ""), 220),
            error=_clip(error_data.get("error", ""), _ERROR_LIMIT),
        )
        if len(prompts.CLASSIFY_ERROR_SYSTEM) + len(payload) > LLM_MAX_REQUEST_CHARS:
            payload = prompts.CLASSIFY_ERROR_USER.format(
                match=_clip(match, _MATCH_LIMIT),
                keyword=_clip(keyword, _MATCH_LIMIT),
                url=_clip(error_data.get("url", ""), _URL_LIMIT),
                title=_clip(error_data.get("title", ""), _TITLE_LIMIT),
                snippet=_clip(error_data.get("snippet", ""), 120),
                error=_clip(error_data.get("error", ""), 120),
            )
        try:
            raw = self._model.call(prompts.CLASSIFY_ERROR_SYSTEM, payload, operation="classify_error")
            return self._parse_label(raw)
        except Exception:
            return _fallback_error_verdict(error_data)
