import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

JINA_BASE_URL = "https://r.jina.ai/"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=15),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
async def fetch_url(url: str, get_links: bool = False) -> str:
    """
    Fetch a URL using Jina AI Reader API.
    Returns clean markdown text of the page.
    """
    jina_url = f"{JINA_BASE_URL}{url}"

    headers = {
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
        "X-Timeout": "25",
    }

    jina_api_key = os.getenv("JINA_API_KEY", "").strip()
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    if get_links:
        headers["X-With-Links-Summary"] = "true"

    logger.debug(f"Jina fetching: {url}")

    async with httpx.AsyncClient(timeout=35.0) as client:
        response = await client.get(jina_url, headers=headers)
        response.raise_for_status()
        content = response.text

    if not content or len(content) < 100:
        raise ValueError(f"Jina returned empty or very short content for {url}")

    logger.debug(f"Jina fetched {len(content)} chars from {url}")
    return content
