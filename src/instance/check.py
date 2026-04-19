from __future__ import annotations

import re
from urllib.parse import urlparse

from ..log import get_logger

log = get_logger("spcrawler.check")

_LIVE_EXTENSIONS = {".m3u8", ".mpd"}

_LIVE_PATH_PATTERNS = [
    r"/hls/",
    r"/live/",
    r"/stream/",
    r"/playlist\.m3u8",
    r"[?&]stream=",
    r"[?&]live=",
    r"/manifest",
    r"/chunklist",
    r"\.ts($|[?#])",        
]

_LIVE_DOMAIN_KEYWORDS = [
    "stream", "live", "hls", "cdn", "cast", "broadcast",
    "crackstream", "methstream", "buffstream", "streameast",
    "hesgoal", "rojadirecta", "acestream", "soccerstream",
    "nbabite", "nflbite", "cricfree",
]

_LIVE_IFRAME_SRC_PATTERNS = [
    r"stream",
    r"live",
    r"embed",
    r"player",
    r"watch",
    r"tv/",
    r"/ch/",
    r"channel",
]

# ── Definite NON-stream indicators (image / tracker / ad / static) ────────────
_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".ico", ".bmp", ".tiff",
}

_STATIC_VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".avi", ".mov", ".mkv"}

_AD_TRACKER_DOMAINS = [
    "doubleclick.net", "googlesyndication.com", "googletagmanager.com",
    "googleadservices.com", "amazon-adsystem.com", "facebook.com/plugins",
    "twitter.com/widgets", "platform.twitter.com", "disqus.com",
    "gravatar.com", "gstatic.com", "fonts.googleapis.com",
    "maps.googleapis.com", "recaptcha.net", "hotjar.com",
    "analytics.google.com", "connect.facebook.net", "adroll.com",
    "outbrain.com", "taboola.com", "adsafeprotected.com",
]

_AD_PATH_PATTERNS = [
    r"/ads?/",
    r"/track(er|ing)?/",
    r"/pixel",
    r"/beacon",
    r"/analytics",
    r"/stat(s|istics)?",
    r"\.gif\?",
]

_SHORT_VIDEO_DOMAINS = [
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
    "twitch.tv",                       # could be live but usually not piracy
    "tiktok.com", "instagram.com",
]


def _path_ext(url: str) -> str:
    """Return lowercase file extension from a URL path, e.g. '.m3u8'."""
    path = urlparse(url).path
    dot  = path.rfind(".")
    if dot == -1:
        return ""
    ext = path[dot:].lower()
    # strip query-string artefacts
    return ext.split("?")[0].split("#")[0]


def is_live_stream_url(url: str) -> bool:
    """
    Return True if *url* looks like a live-stream manifest or segment.
    Conservative: only returns True when there's positive evidence.
    """
    if not url:
        return False

    url_lower = url.lower()
    parsed    = urlparse(url_lower)

    # Explicit non-stream schemes → reject immediately
    if parsed.scheme in ("data", "blob", "javascript", "mailto"):
        return False

    # Explicit live-stream schemes
    if parsed.scheme in ("rtmp", "rtmpe", "rtmps", "rtmpt", "rtmpte",
                         "acestream", "sopcast"):
        log.debug("live-stream scheme: %s", url[:80])
        return True

    ext = _path_ext(url)

    # Image → definitely not a stream
    if ext in _IMAGE_EXTENSIONS:
        return False

    # Known live-stream extension
    if ext in _LIVE_EXTENSIONS:
        log.debug("live-stream ext %s: %s", ext, url[:80])
        return True

    # Static video file → not a live stream (could be VOD clip)
    if ext in _STATIC_VIDEO_EXTENSIONS:
        return False

    domain = parsed.netloc

    # Ad/tracker domains → not streams
    for ad in _AD_TRACKER_DOMAINS:
        if ad in domain:
            return False

    # Well-known non-piracy video platforms → not the target
    for vd in _SHORT_VIDEO_DOMAINS:
        if vd in domain:
            return False

    # Positive: path matches live-stream patterns
    for pat in _LIVE_PATH_PATTERNS:
        if re.search(pat, url_lower):
            log.debug("live-stream path pattern '%s': %s", pat, url[:80])
            return True

    # Positive: domain contains live-stream keyword
    for kw in _LIVE_DOMAIN_KEYWORDS:
        if kw in domain:
            log.debug("live-stream domain keyword '%s': %s", kw, url[:80])
            return True

    return False


def is_live_stream_iframe(src: str) -> bool:
    """
    Return True if an <iframe src="…"> looks like a live-stream embed
    rather than an image widget, social plugin, or static video.
    """
    if not src:
        return False

    src_lower = src.lower()
    parsed    = urlparse(src_lower)
    domain    = parsed.netloc

    # Reject data-URIs, blobs, JS
    if parsed.scheme in ("data", "blob", "javascript", "mailto"):
        return False

    # Ad / tracker / social plugin → skip
    for ad in _AD_TRACKER_DOMAINS:
        if ad in domain:
            return False

    # Well-known short-video platforms → skip
    for vd in _SHORT_VIDEO_DOMAINS:
        if vd in domain:
            return False

    # If the URL itself is a live stream → yes
    if is_live_stream_url(src):
        return True

    # Path or query contains iframe live-stream hints
    path_and_query = parsed.path + "?" + (parsed.query or "")
    for pat in _LIVE_IFRAME_SRC_PATTERNS:
        if re.search(pat, path_and_query):
            log.debug("live-stream iframe pattern '%s': %s", pat, src[:80])
            return True

    # Domain keyword match
    for kw in _LIVE_DOMAIN_KEYWORDS:
        if kw in domain:
            return True

    return False


def filter_live_stream_iframes(iframes: list[str]) -> list[str]:
    """Filter a list of iframe src URLs, returning only live-stream candidates."""
    result = [src for src in iframes if is_live_stream_iframe(src)]
    log.debug("iframe filter: %d/%d passed", len(result), len(iframes))
    return result


def filter_live_stream_urls(urls: list[str]) -> list[str]:
    """Filter a list of URLs, returning only live-stream candidates."""
    result = [u for u in urls if is_live_stream_url(u)]
    log.debug("url filter: %d/%d passed", len(result), len(urls))
    return result


def extract_best_live_stream(page_data: dict) -> str | None:
    """
    Given page_data dict, return the single best live-stream URL found,
    preferring .m3u8 manifests, then rtmp://, then other live URLs.
    Returns None if nothing qualifies.
    """
    candidates: list[str] = []

    # 1. scheme_urls (already extracted from HTML / network traffic)
    candidates += filter_live_stream_urls(page_data.get("scheme_urls", []))

    # 2. iframes that look like live-stream embeds
    candidates += filter_live_stream_iframes(page_data.get("iframes", []))

    if not candidates:
        return None

    # Prefer .m3u8 manifests
    for url in candidates:
        if ".m3u8" in url.lower():
            return url

    # Then rtmp
    for url in candidates:
        if url.lower().startswith("rtmp"):
            return url

    return candidates[0]