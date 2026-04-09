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
# Replace the entire fetch_url_as_markdown function with:
async def fetch_url_as_markdown(url: str) -> str:
    """Fetch via urltomarkdown public API with proper encoding + sanitization"""
    # Sanitize Zillow-specific URL artifacts
    clean_url = url.rstrip(')/').rstrip('/') + '/'
    
    async with httpx.AsyncClient(timeout=90) as client:
        # Let httpx handle encoding via params dict
        resp = await client.get(
            "https://urltomarkdown.herokuapp.com/",
            params={
                "url": clean_url,  # raw URL - httpx encodes safely
                "clean": "false",
                "links": "true", 
                "title": "false"
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/plain"
            }
        )
        resp.raise_for_status()
        return resp.text.strip()
