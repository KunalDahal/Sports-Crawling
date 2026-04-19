import asyncio
import os
from dotenv import load_dotenv

from src.log import get_logger, setup
from src import Scraper

load_dotenv()

setup(level=os.getenv("LOG_LEVEL", "info"))

log = get_logger("spcrawler.run")

API_KEY   = os.getenv("GEMINI_API_KEY", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "sports_scraper")
PROXY_URL = os.getenv("PROXY_URL", "")


async def main() -> None:
    scraper = Scraper(
        keyword   = "RR vs KKR watch free live",
        api_key   = API_KEY,
        db_name   = DB_NAME,
        mongo_uri = MONGO_URI,
        proxy_url = PROXY_URL,
    )

    m3u8 = await scraper.run()

    if m3u8:
        log.info("Result: %s", m3u8)
    else:
        log.warning("No stream found.")


if __name__ == "__main__":
    asyncio.run(main())
