"""
Scraper client using urltomarkdown.herokuapp.com
Returns clean markdown — much lighter for the LLM to parse than raw HTML.
"""
import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

TIMEOUT = 60.0
BASE = "https://urltomarkdown.herokuapp.com/"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=20),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
async def fetch_url(url: str, get_links: bool = False) -> str:
    """
    Fetch a URL via urltomarkdown and return clean markdown.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            BASE,
            params={
                "url": url,
                "clean": "false",   # keep all content including links
            },
        )
        resp.raise_for_status()
        content = resp.text

    if not content or len(content) < 100:
        raise ValueError(f"urltomarkdown returned empty content for {url}")

    logger.info(f"[urltomarkdown] ✓ {len(content):,} chars from {url[:60]}")
    return content
