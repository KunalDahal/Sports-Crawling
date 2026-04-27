from __future__ import annotations

import asyncio
import copy
import re
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse, urlsplit, urlunsplit
from uuid import uuid4

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from ddgs import DDGS

from ..client.llm import LLM
from ..client.model import get_model
from ..utils.config import Config
from ..utils.constants import (
    AD_DOMAIN_HINTS,
    BETWEEN_SEARCHES_SEC,
    CRAWL_TIMEOUT_SEC,
    DDGS_PER_TURN,
    DDGS_SEARCH_QUERIES,
    DDGS_TURN_DELAY,
    DDGS_TURNS,
    HEADLESS_BROWSER,
    MAX_DEPTH,
    MAX_LINKS_PER_PAGE,
    MAX_ROOTS_PER_KEYWORD,
    MAX_STREAM_URLS,
    MAX_TOTAL_PAGES,
    OFFICIAL_DOMAIN_HINTS,
    REQUEST_TIMEOUT_MS,
    USER_AGENT,
)
from .proxy_manager import ProxyManager

_CRAWL_RETRIES = 2
_RETRY_DELAY = 1.5
_STREAM_URL_RE = re.compile(
    r'(?i)(https?://[^\s"\'<>]+?(?:\.m3u8|\.mpd)(?:\?[^\s"\'<>]*)?|acestream://[A-Za-z0-9]+)'
)
_STREAM_HINT_RE = re.compile(r"(?i)(\.m3u8|\.mpd|/hls/|manifest|chunklist|playlist|acestream)")
_AD_PATH_RE = re.compile(
    r"(?i)(/ads?[/?._-]|advert|banner|popup|popunder|preroll|vast|vpaid|ima3|tracker|analytics|pixel|doubleclick)"
)

UpdateCallback = Callable[[dict], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def _canonical_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except Exception:
        return url.strip()
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _keyword_url_key(keyword_id: str, url: str) -> str:
    return f"{keyword_id}:{_canonical_url(url)}"


def _official_domain_hint(url: str) -> str:
    host = _hostname(url).lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    for hint in OFFICIAL_DOMAIN_HINTS:
        normalized = hint.lower().strip(".")
        if host == normalized or host.endswith(f".{normalized}"):
            return normalized
    return ""


def _domain_hint(url: str, hints: tuple[str, ...]) -> str:
    host = _hostname(url).lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    for hint in hints:
        normalized = hint.lower().strip(".")
        if host == normalized or host.endswith(f".{normalized}"):
            return normalized
    return ""


def _looks_like_ad_url(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    if _domain_hint(raw, AD_DOMAIN_HINTS):
        return True
    return _AD_PATH_RE.search(raw) is not None


def _dedupe_urls(urls: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in urls:
        url = value.strip()
        if not url:
            continue
        key = _canonical_url(url)
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _looks_like_stream_url(url: str) -> bool:
    raw = str(url or "").strip()
    if raw.lower().startswith("acestream://"):
        return True
    if not raw.lower().startswith(("http://", "https://")):
        return False
    return _STREAM_HINT_RE.search(raw) is not None


def _extract_stream_urls(html: str, links: list[dict], iframes: list[str], network_urls: list[str]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(match.group(1) for match in _STREAM_URL_RE.finditer(html) if not _looks_like_ad_url(match.group(1)))
    for url in iframes:
        if _looks_like_stream_url(url) and not _looks_like_ad_url(url):
            candidates.append(url)
    for link in links:
        url = link.get("url", "")
        if _looks_like_stream_url(url) and not _looks_like_ad_url(url):
            candidates.append(url)
    for url in network_urls:
        if _looks_like_stream_url(url) and not _looks_like_ad_url(url):
            candidates.append(url)
    return _dedupe_urls(candidates, limit=MAX_STREAM_URLS)


def _make_keywords(match: str) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for template in DDGS_SEARCH_QUERIES:
        value = template.format(keyword=match, match=match).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            keywords.append(value)
    return keywords


def _is_url(value: str) -> bool:
    raw = str(value or "").strip().lower()
    return raw.startswith(("http://", "https://"))


def _multi_search(query: str) -> list[dict]:
    seen: set[str] = set()
    results: list[dict] = []

    for turn in range(DDGS_TURNS):
        try:
            with DDGS() as ddgs:
                raw = ddgs.text(query, max_results=DDGS_PER_TURN)
            for item in raw or []:
                url = item.get("href", "")
                if not url.startswith("http") or url in seen:
                    continue
                seen.add(url)
                results.append({"url": url, "title": item.get("title", "")})
                if len(results) >= MAX_ROOTS_PER_KEYWORD:
                    return results
        except Exception:
            pass

        if turn < DDGS_TURNS - 1:
            time.sleep(DDGS_TURN_DELAY)

    return results


def _extract_text(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    size = 0
    for line in lines:
        value = line.strip()
        if not value:
            continue
        if value.startswith("#"):
            continue
        if value.startswith("http://") or value.startswith("https://"):
            continue
        out.append(value)
        size += len(value)
        if size >= 360:
            break
    return " ".join(out)[:360].strip()


def _extract_page(result, url: str) -> dict:
    page_url = _canonical_url(url)
    html = result.html or ""
    raw_md = ""
    if result.markdown:
        try:
            raw_md = result.markdown.raw_markdown
        except AttributeError:
            raw_md = str(result.markdown)

    links: list[dict] = []
    seen_urls: set[str] = set()
    for group in ("internal", "external"):
        for link in (result.links or {}).get(group, []):
            href = link.get("href", "")
            canonical_href = _canonical_url(href)
            if (
                not href.startswith("http")
                or _looks_like_ad_url(href)
                or canonical_href == page_url
                or canonical_href in seen_urls
            ):
                continue
            seen_urls.add(canonical_href)
            links.append({"url": href, "title": (link.get("text", "") or "").strip()})
            if len(links) >= MAX_LINKS_PER_PAGE:
                break
        if len(links) >= MAX_LINKS_PER_PAGE:
            break

    iframes = [
        url
        for url in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not _looks_like_ad_url(url)
    ]
    network_urls: list[str] = []
    for item in getattr(result, "network_requests", []) or []:
        if isinstance(item, dict):
            request_url = item.get("url", "")
        else:
            request_url = getattr(item, "url", "")
        if isinstance(request_url, str) and request_url and not _looks_like_ad_url(request_url):
            network_urls.append(request_url)

    return {
        "url": url,
        "title": (result.metadata or {}).get("title", "") or _hostname(url),
        "text_snippet": _extract_text(raw_md),
        "links_found": links,
        "iframes": list(dict.fromkeys(iframes))[:20],
        "stream_urls": _extract_stream_urls(html, links, iframes, network_urls),
    }


class SPCrawler:
    """Dedicated crawler for one received URL."""

    def __init__(self, link: str, api_key: str = "", proxy_url: str = "") -> None:
        self.link = link.strip()
        self.api_key = api_key
        self.proxy_url = proxy_url
        cfg = Config(api_key=api_key, proxy_url=proxy_url)
        self._proxy = ProxyManager(cfg)

    def browser_config(self) -> BrowserConfig:
        proxy = self._proxy.get()
        return BrowserConfig(
            headless=HEADLESS_BROWSER,
            user_agent=USER_AGENT,
            verbose=False,
            memory_saving_mode=True,
            enable_stealth=True,
            ignore_https_errors=True,
            **({"proxy": proxy["server"]} if proxy else {}),
        )

    @staticmethod
    def run_config() -> CrawlerRunConfig:
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=REQUEST_TIMEOUT_MS,
            screenshot=False,
            wait_until="domcontentloaded",
            process_iframes=True,
            capture_network_requests=True,
            verbose=False,
            word_count_threshold=5,
            remove_overlay_elements=True,
            simulate_user=True,
        )

    async def crawl(
        self,
        crawler: AsyncWebCrawler | None = None,
        run_cfg: CrawlerRunConfig | None = None,
    ) -> tuple[dict | None, dict]:
        if crawler is None:
            async with AsyncWebCrawler(config=self.browser_config()) as owned_crawler:
                return await self._crawl_with(owned_crawler, run_cfg or self.run_config())
        return await self._crawl_with(crawler, run_cfg or self.run_config())

    async def _crawl_with(
        self,
        crawler: AsyncWebCrawler,
        run_cfg: CrawlerRunConfig,
    ) -> tuple[dict | None, dict]:
        error_data = {
            "url": self.link,
            "title": "",
            "snippet": "",
            "error": "",
        }
        for attempt in range(1, _CRAWL_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    crawler.arun(url=self.link, config=run_cfg),
                    timeout=CRAWL_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                error_data["error"] = f"Timeout after {attempt} attempt(s)"
                if attempt < _CRAWL_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                return None, error_data
            except Exception as exc:
                error_data["error"] = str(exc)
                if attempt < _CRAWL_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                return None, error_data

            if not result.success:
                error = result.error_message or ""
                error_data["title"] = (result.metadata or {}).get("title", "") if getattr(result, "metadata", None) else ""
                if getattr(result, "markdown", None):
                    try:
                        error_data["snippet"] = _extract_text(result.markdown.raw_markdown)
                    except AttributeError:
                        error_data["snippet"] = _extract_text(str(result.markdown))
                error_data["error"] = error or f"Unknown crawl failure on attempt {attempt}"
                if attempt < _CRAWL_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                return None, error_data

            return _extract_page(result, self.link), error_data
        return None, error_data


spcrawler = SPCrawler


class Scraper:
    def __init__(
        self,
        match: str = "",
        link: str = "",
        api_key: str = "",
        proxy_url: str = "",
        session_id: str = "",
        on_update: UpdateCallback | None = None,
        keyword: str = "",
    ) -> None:
        self.match = (match or keyword or link).strip()
        self.link = (link or (self.match if _is_url(self.match) else "")).strip()
        self.api_key = api_key
        self.proxy_url = proxy_url
        self.session_id = session_id or uuid4().hex
        self._on_update = on_update
        self._visited_urls: set[str] = set()
        self._node_by_id: dict[str, dict] = {}
        self._node_by_url: dict[str, str] = {}
        self._root_ids: list[str] = []
        self._node_seq = 0

        cfg = Config(api_key=api_key, proxy_url=proxy_url)
        self._llm = LLM(get_model(cfg))

        self._state = {
            "session_id": self.session_id,
            "match": self.match,
            "status": "idle",
            "message": "",
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

    def snapshot(self) -> dict:
        return copy.deepcopy(self._state)

    def run_sync(self, on_update: UpdateCallback | None = None) -> dict:
        return asyncio.run(self.run(on_update=on_update))

    async def run(self, on_update: UpdateCallback | None = None) -> dict:
        if on_update is not None:
            self._on_update = on_update

        self._state["status"] = "running"
        self._state["started_at"] = _now()
        self._state["message"] = "Preparing crawl"
        self._push()

        try:
            if self.link:
                keyword = self._add_keyword(self.link)
                await self._run_keyword(keyword)
                self._state["status"] = "finished"
                self._state["message"] = "Finished"
                self._state["finished_at"] = _now()
                self._push()
            else:
                while True:
                    keyword = self._add_keyword(self._next_keyword())
                    await self._run_keyword(keyword)
                    self._state["message"] = "Keyword complete; generating next keyword"
                    self._push()
            return self.snapshot()
        except Exception as exc:
            self._state["status"] = "failed"
            self._state["error"] = str(exc)
            self._state["message"] = "Failed"
            self._state["finished_at"] = _now()
            self._push()
            return self.snapshot()

    def _next_keyword(self) -> str:
        previous = [keyword["query"] for keyword in self._state["keywords"]]
        if previous:
            self._state["message"] = "LLM next keyword"
            self._push()
            query = self._llm.make_next_keyword(self.match, previous)
        else:
            self._state["message"] = "LLM keyword summary"
            self._push()
            query = self._llm.make_keyword(self.match)
        return _make_keywords(query)[0]

    def _add_keyword(self, query: str) -> dict:
        normalized = query.strip()
        previous = {keyword["query"].lower() for keyword in self._state["keywords"]}
        if normalized.lower() in previous:
            normalized = f"{normalized} alternate {len(previous) + 1}"

        keyword_id = f"keyword:{len(self._state['keywords']) + 1}"
        keyword = {
            "id": keyword_id,
            "query": normalized,
            "search_results": 0,
            "status": "pending",
            "started_at": "",
            "finished_at": "",
            "root_ids": [],
            "node_ids": [],
            "stats": {
                "roots": 0,
                "visited": 0,
                "official": 0,
                "suspicious": 0,
                "clean": 0,
            },
            "result": {
                "node_ids": [],
                "stats": {
                    "roots": 0,
                    "visited": 0,
                    "official": 0,
                    "suspicious": 0,
                    "clean": 0,
                },
            },
        }
        self._state["keywords"].append(keyword)
        self._state["active_keyword_id"] = keyword_id
        self._state["message"] = "Keyword ready"
        self._push()
        return keyword

    async def _run_keyword(self, keyword: dict) -> None:
        self._state["active_keyword_id"] = keyword["id"]
        keyword["status"] = "running"
        keyword["started_at"] = _now()
        self._push()
        await self._search_roots_for_keyword(keyword)
        await self._walk_keyword(keyword["id"])
        keyword["status"] = "finished"
        keyword["finished_at"] = _now()
        self._push()

    def _keyword_query(self, keyword_id: str) -> str:
        for keyword in self._state["keywords"]:
            if keyword["id"] == keyword_id:
                return keyword["query"]
        return self.match

    async def _search_roots_for_keyword(self, keyword: dict) -> None:
        if self.link:
            node_id, created = self._add_node(
                url=self.link,
                title=_hostname(self.link),
                parent_id=keyword["id"],
                keyword_id=keyword["id"],
                depth=0,
                is_root=True,
            )
            if created:
                self._root_ids.append(node_id)
                keyword["root_ids"].append(node_id)
            keyword["search_results"] = 1
            self._state["message"] = "Dedicated link ready"
            self._push()
            return

        self._state["error"] = ""
        self._state["message"] = f"Searching {keyword['query']}"
        self._push()
        results = await asyncio.to_thread(_multi_search, keyword["query"])
        keyword["search_results"] = len(results)
        self._state["message"] = "LLM search result filter"
        self._push()
        selected_urls = await asyncio.to_thread(
            self._llm.filter_search_results,
            self.match,
            keyword["query"],
            results,
        )
        selected = [item for item in results if item["url"] in set(selected_urls)]
        for item in selected:
            node_id, created = self._add_node(
                url=item["url"],
                title=item.get("title", "") or _hostname(item["url"]),
                parent_id=keyword["id"],
                keyword_id=keyword["id"],
                depth=0,
                is_root=True,
            )
            if created:
                self._root_ids.append(node_id)
                keyword["root_ids"].append(node_id)
        self._push()
        await asyncio.sleep(BETWEEN_SEARCHES_SEC)

    async def _walk_keyword(self, keyword_id: str) -> None:
        root_ids = self._keyword_root_ids(keyword_id)
        if not root_ids:
            self._state["message"] = "No search results"
            self._push()
            return

        page_crawler = SPCrawler("", self.api_key, self.proxy_url)
        browser_cfg = page_crawler.browser_config()
        run_cfg = page_crawler.run_config()

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            for root_id in root_ids:
                if self._keyword_stats(keyword_id)["visited"] >= MAX_TOTAL_PAGES:
                    break
                await self._walk_root(crawler, run_cfg, root_id, keyword_id)

    async def _walk_root(
        self,
        crawler: AsyncWebCrawler,
        run_cfg: CrawlerRunConfig,
        root_id: str,
        keyword_id: str,
    ) -> None:
        stack = [root_id]
        while stack and self._keyword_stats(keyword_id)["visited"] < MAX_TOTAL_PAGES:
            node_id = stack.pop()
            node = self._node_by_id.get(node_id)
            if not node:
                continue
            node_key = _keyword_url_key(keyword_id, node["url"])
            if node_key in self._visited_urls:
                continue
            if node["depth"] > MAX_DEPTH:
                continue

            page = await self._inspect_node(crawler, run_cfg, node)
            if not page:
                continue

            if node["classification"] != "suspicious":
                continue

            self._state["message"] = "Expanding child links"
            self._push()
            next_ids: list[str] = []
            parent_url = _canonical_url(node["url"])
            for link in page.get("selected_links", page["links_found"]):
                if _canonical_url(link.get("url", "")) == parent_url:
                    continue
                child_id, created = self._add_node(
                    url=link["url"],
                    title=link.get("title", "") or _hostname(link["url"]),
                    parent_id=node["id"],
                    keyword_id=node["keyword_id"],
                    depth=node["depth"] + 1,
                    is_root=False,
                )
                if created:
                    next_ids.append(child_id)

            node["child_ids"] = next_ids
            self._push()

            for child_id in reversed(next_ids):
                stack.append(child_id)

    async def _inspect_node(
        self,
        crawler: AsyncWebCrawler,
        run_cfg: CrawlerRunConfig,
        node: dict,
    ) -> dict | None:
        node["status"] = "visiting"
        self._state["error"] = ""
        self._state["current_node_id"] = node["id"]
        self._state["current_url"] = node["url"]
        self._state["active_keyword_id"] = node["keyword_id"]
        official_hint = _official_domain_hint(node["url"])
        if official_hint:
            node["classification"] = "official"
            node["reason"] = f"official domain {official_hint}"
            node["color"] = "blue"
            node["status"] = "done"
            node["visited"] = True
            node["links"] = []
            node["iframes"] = []
            node["stream_urls"] = []
            self._state["message"] = "Official domain detected"
            self._visited_urls.add(_keyword_url_key(node["keyword_id"], node["url"]))
            self._push()
            return None
        self._state["message"] = "Scraping page"
        self._push()

        page, error_data = await self._crawl_page(crawler, run_cfg, node["url"])
        keyword_query = self._keyword_query(node["keyword_id"])
        if page is None:
            self._state["message"] = "LLM error check"
            self._push()
            verdict = await asyncio.to_thread(self._llm.classify_error, self.match, keyword_query, error_data)
            node["title"] = error_data.get("title", "") or node["title"]
            node["summary"] = error_data.get("snippet", "")
            node["links"] = []
            node["iframes"] = []
            node["stream_urls"] = []
            node["classification"] = verdict["label"]
            node["reason"] = verdict["reason"] or error_data.get("error", "Could not open page")
            node["color"] = {
                "official": "blue",
                "suspicious": "red",
                "clean": "green",
            }[verdict["label"]]
            node["status"] = "error"
            node["visited"] = True
            self._state["error"] = error_data.get("error", "Could not open page")
            self._state["message"] = "Page open failed"
            self._visited_urls.add(_keyword_url_key(node["keyword_id"], node["url"]))
            self._push()
            return None

        self._state["message"] = "Scrape done"
        self._push()
        self._state["message"] = "LLM page check"
        self._push()
        verdict = await asyncio.to_thread(self._llm.classify_node, self.match, keyword_query, page)
        node["title"] = page["title"]
        node["summary"] = page["text_snippet"]
        node["links"] = page["links_found"]
        node["iframes"] = page["iframes"]
        node["stream_urls"] = page["stream_urls"]
        node["classification"] = verdict["label"]
        node["reason"] = verdict["reason"]
        selected_urls = set(verdict.get("next_links", []))
        if selected_urls:
            page["selected_links"] = [link for link in page["links_found"] if link.get("url", "") in selected_urls]
        else:
            page["selected_links"] = []
        node["color"] = {
            "official": "blue",
            "suspicious": "red",
            "clean": "green",
        }[verdict["label"]]
        node["status"] = "done"
        node["visited"] = True
        self._state["error"] = ""
        self._state["message"] = "Classification done"
        self._visited_urls.add(_keyword_url_key(node["keyword_id"], node["url"]))
        self._push()
        return page

    async def _crawl_page(
        self,
        crawler: AsyncWebCrawler,
        run_cfg: CrawlerRunConfig,
        url: str,
    ) -> tuple[dict | None, dict]:
        return await SPCrawler(url, self.api_key, self.proxy_url).crawl(crawler, run_cfg)

    def _add_node(
        self,
        url: str,
        title: str,
        parent_id: str,
        keyword_id: str,
        depth: int,
        is_root: bool,
    ) -> tuple[str, bool]:
        url_key = _keyword_url_key(keyword_id, url)
        existing_id = self._node_by_url.get(url_key)
        if existing_id:
            return existing_id, False

        self._node_seq += 1
        node_id = f"node:{self._node_seq}"
        node = {
            "id": node_id,
            "parent_id": parent_id,
            "keyword_id": keyword_id,
            "root": is_root,
            "depth": depth,
            "url": url,
            "title": title,
            "summary": "",
            "links": [],
            "iframes": [],
            "stream_urls": [],
            "child_ids": [],
            "classification": "pending",
            "color": "yellow",
            "reason": "",
            "status": "pending",
            "visited": False,
        }
        self._node_by_url[url_key] = node_id
        self._node_by_id[node_id] = node
        self._state["nodes"].append(node)
        keyword = self._keyword_by_id(keyword_id)
        if keyword is not None:
            keyword["node_ids"].append(node_id)
        return node_id, True

    def _keyword_by_id(self, keyword_id: str) -> dict | None:
        for keyword in self._state["keywords"]:
            if keyword["id"] == keyword_id:
                return keyword
        return None

    def _keyword_root_ids(self, keyword_id: str) -> list[str]:
        keyword = self._keyword_by_id(keyword_id)
        if keyword is not None:
            return list(keyword.get("root_ids", []))
        return [node["id"] for node in self._state["nodes"] if node["keyword_id"] == keyword_id and node["root"]]

    def _keyword_stats(self, keyword_id: str) -> dict:
        stats = {
            "roots": 0,
            "visited": 0,
            "official": 0,
            "suspicious": 0,
            "clean": 0,
        }
        for node in self._state["nodes"]:
            if node["keyword_id"] != keyword_id:
                continue
            if node["root"]:
                stats["roots"] += 1
            if node["visited"]:
                stats["visited"] += 1
            if node["classification"] in stats:
                stats[node["classification"]] += 1
        return stats

    def _push(self) -> None:
        stats = {
            "keywords": len(self._state["keywords"]),
            "roots": len(self._root_ids),
            "visited": 0,
            "official": 0,
            "suspicious": 0,
            "clean": 0,
        }
        for node in self._state["nodes"]:
            if node["visited"]:
                stats["visited"] += 1
            if node["classification"] in stats:
                stats[node["classification"]] += 1
        self._state["stats"] = stats

        for keyword in self._state["keywords"]:
            keyword_stats = self._keyword_stats(keyword["id"])
            keyword["stats"] = keyword_stats
            keyword["result"] = {
                "node_ids": list(keyword.get("node_ids", [])),
                "stats": keyword_stats,
            }

        if self._on_update is None:
            return
        self._on_update(self.snapshot())
