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
# core/scraper_client.py
import httpx
import asyncio

async def fetch_url(url: str, max_retries: int = 2) -> str:
    """
    Fetch Zillow profile as markdown via public urltomarkdown API.
    Critical: Remove trailing )/ AND / to match browser behavior.
    """
    # === SANITIZE ZILLOW URLS ===
    # Remove trailing artifacts: ")/" → "/" → ""
    clean_url = url.rstrip(')/').rstrip('/')
    
    # Ensure it's still a valid http URL
    if not clean_url.startswith('http'):
        clean_url = 'https://' + clean_url.lstrip('/')
    
    for attempt in range(max_retries +  1):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                # ✅ KEY FIX: Pass params as dict → httpx handles encoding safely
                # ✅ NO manual quote() → prevents double-encoding
                resp = await client.get(
                    "https://urltomarkdown.herokuapp.com/",
                    params={
                        "url": clean_url,      # raw string, httpx encodes
                        "clean": "false",
                        "links": "true",
                        "title": "false"
                    },
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/plain"
                    }
                )
                
                # Handle rate limiting
                if resp.status_code == 429:
                    wait = 8 * (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                    
                resp.raise_for_status()
                return resp.text.strip()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [502, 503, 504]:
                if attempt < max_retries:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
            raise
        except httpx.RequestError as e:
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    
    raise RuntimeError(f"Failed to fetch {clean_url} after {max_retries} retries")
