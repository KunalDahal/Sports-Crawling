from .instance.proxy_manager import ProxyManager
from .instance.scraper import SPCrawler, Scraper
from .engine import EngineRequest, empty_state, run_request

spcrawler = SPCrawler

__all__ = ["EngineRequest", "Scraper", "SPCrawler", "empty_state", "run_request", "spcrawler", "ProxyManager"]
