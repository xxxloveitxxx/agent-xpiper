# core/scraper_client.py
import httpx
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TIMEOUT = 90.0
BASE_URL = "https://urltomarkdown.herokuapp.com/"


def _sanitize_zillow_url(url: str) -> str:
    """Remove trailing )/ or / artifacts from Zillow profile URLs."""
    clean = url.rstrip(')/').rstrip('/')
    if not clean.startswith('http'):
        clean = 'https://' + clean.lstrip('/')
    return clean


async def fetch_url(url: str, max_retries: int = 2) -> str:
    """
    Fetch webpage as markdown via public urltomarkdown API.
    Handles Zillow URL quirks, rate limits, and transient errors.
    """
    clean_url = _sanitize_zillow_url(url)
    
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # ✅ httpx auto-encodes params safely - NO manual quote()
                resp = await client.get(
                    BASE_URL,
                    params={
                        "url": clean_url,
                        "clean": "false",
                        "links": "true",
                        "title": "false"
                    },
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/plain"
                    }
                )
                
                # Handle rate limiting (429)
                if resp.status_code == 429:
                    wait_time = 8 * (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt+1}/{max_retries}")
                    await asyncio.sleep(wait_time)
                    continue
                
                # Raise for other HTTP errors (502, 503, etc.)
                resp.raise_for_status()
                return resp.text.strip()
                
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in [502, 503, 504] and attempt < max_retries:
                wait_time = 3 * (attempt + 1)
                logger.warning(f"Server error {status}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            logger.error(f"HTTP error {status} for {clean_url}: {e}")
            raise
            
        except httpx.RequestError as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.warning(f"Request error, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
                continue
            logger.error(f"Request failed after {max_retries}
