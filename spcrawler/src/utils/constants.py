from __future__ import annotations

LLM_MODEL = "gemini-2.5-flash-lite"
LLM_MAX_TOKENS = 512
LLM_TEMPERATURE = 0.2
LLM_MAX_RETRIES = 2
MIN_DELAY_BETWEEN_LLM_CALLS = 0.5
LLM_BACKOFF_BASE = 2
LLM_BACKOFF_MAX = 8
LLM_RATE_LIMIT_COOLDOWN = 4.0
LLM_REQUEST_TIMEOUT_SEC = 10
LLM_MAX_REQUEST_CHARS = 3200

HEADLESS_BROWSER = True
REQUEST_TIMEOUT_MS = 20_000
CRAWL_TIMEOUT_SEC = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DDGS_TURNS = 7
DDGS_PER_TURN = 15
DDGS_TURN_DELAY = 3.0
DDGS_SEARCH_QUERIES = [
    "{keyword}",
]

OFFICIAL_DOMAIN_HINTS = (
    "hotstar.com",
    "disneyplus.com",
    "disneyplushotstar.com",
    "jiocinema.com",
    "sonyliv.com",
    "espn.com",
    "espn.in",
    "espncricinfo.com",
    "iplt20.com",
    "icc-cricket.com",
    "bcci.tv",
    "willow.tv",
    "fancode.com",
)

MAX_ROOTS_PER_KEYWORD = 20
MAX_LINKS_PER_PAGE = 100
MAX_STREAM_URLS = 5
MAX_DEPTH = 10
MAX_TOTAL_PAGES = 100
BETWEEN_SEARCHES_SEC = 1.0

AD_DOMAIN_HINTS = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "adnxs.com",
    "taboola.com",
    "outbrain.com",
    "popads.net",
    "propellerads.com",
    "onclickads.net",
    "adsterra.com",
    "exoclick.com",
    "mgid.com",
)
