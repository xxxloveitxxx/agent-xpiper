# core/scraper_client.py
import httpx
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://urltomarkdown.herokuapp.com/"
TIMEOUT = 35  # Slightly above Heroku's 30s limit


def _sanitize_zillow_url(url: str) -> str:
    """Remove trailing )/ or / artifacts from Zillow profile URLs."""
    clean = url.rstrip(')/').rstrip('/')
    if not clean.startswith('http'):
        clean = 'https://' + clean.lstrip('/')
    return clean


async def fetch_url(url: str, max_retries: int = 3) -> str:
    """
    Fetch webpage as markdown via public urltomarkdown API.
    Implements your retry strategy for 429/502 errors.
    """
    clean_url = _sanitize_zillow_url(url)
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
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
                
                # === HANDLE 429: Rate Limited ===
                if resp.status_code == 429:
                    # Check Retry-After header first
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        # Your recommendation: 60s base, exponential
                        wait_time = 60 * (2 ** attempt)
                    
                    logger.warning(f"429 Rate limited. Waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                
                # === HANDLE 502/503/504: Bad Gateway ===
                if resp.status_code in [502, 503, 504]:
                    # Your recommendation: 10s → 30s → 60s
                    wait_times = [10, 30, 60]
                    wait_time = wait_times[attempt] if attempt < len(wait_times) else 60
                    
                    logger.warning(f"{resp.status_code} Gateway error. Waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                
                # Success!
                resp.raise_for_status()
                return resp.text.strip()
                
        except httpx.TimeoutException:
            wait_time = 15 * (attempt + 1)
            logger.warning(f"Timeout. Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
            continue
            
        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
                continue
            logger.error(f"Request failed after {max_retries} attempts: {e}")
            raise
    
    raise RuntimeError(f"Failed to fetch {clean_url} after {max_retries} retries")
