# core/scraper_client.py
import httpx
import asyncio
import logging
import os
import random
from typing import Optional, List

logger = logging.getLogger(__name__)

BASE_URL = "https://urltomarkdown.herokuapp.com/"
TIMEOUT = 35

def init_proxies(webshare_api_key: str, proxy_count: int = 10) -> bool:
    """
    Initialize Webshare proxy rotation.
    Call this ONCE at app startup (e.g., in main.py).
    
    Returns: True if proxies loaded successfully, False otherwise.
    """
    global proxy_manager
    try:
        proxy_manager = WebshareProxyManager(
            api_key=webshare_api_key,
            proxy_count=proxy_count
        )
        # Pre-load proxies asynchronously (fire-and-forget for startup)
        asyncio.create_task(proxy_manager.refresh())
        logger.info("✓ Webshare proxy manager initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to init proxies: {e}")
        return False
        
# === Load & Parse Webshare Proxies ===
def _load_proxies() -> List[dict]:
    """Parse WEBSHARE_PROXIES env var into httpx-compatible proxy configs."""
    proxies = []
    raw = os.getenv("WEBSHARE_PROXIES", "").strip()
    if not raw:
        return proxies
    
    for line in raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            host, port, username, password = line.split(":")
            proxy_url = f"http://{username}:{password}@{host}:{port}"
            proxies.append({
                "http://": proxy_url,
                "https://": proxy_url
            })
        except ValueError:
            logger.warning(f"Skipping invalid proxy config: {line}")
    return proxies

PROXIES = _load_proxies()
logger.info(f"Loaded {len(PROXIES)} Webshare.io proxies")


def _sanitize_zillow_url(url: str) -> str:
    """Remove trailing )/ or / artifacts from Zillow profile URLs."""
    clean = url.rstrip(')/').rstrip('/')
    if not clean.startswith('http'):
        clean = 'https://' + clean.lstrip('/')
    return clean


async def fetch_url(url: str, max_retries: int = 2) -> str:
    """
    Fetch webpage as markdown via urltomarkdown API with proxy rotation.
    """
    clean_url = _sanitize_zillow_url(url)
    
    for attempt in range(max_retries + 1):
        # === Rotate proxy (random selection) ===
        proxy_config = random.choice(PROXIES) if PROXIES else None
        
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT,
                proxies=proxy_config  # httpx handles auth via proxy URL
            ) as client:
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
                        "Accept": "text/plain",
                        "Referer": "https://www.zillow.com/"
                    }
                )
                
                # === Handle 429: Rate Limited ===
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else 60 * (2 ** attempt)
                    logger.warning(f"429 on proxy {proxy_config['http://'][:30]}... Waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                
                # === Handle 502/503/504: Gateway Errors ===
                if resp.status_code in [502, 503, 504]:
                    if attempt < max_retries:
                        wait_time = [15, 30, 60][attempt] if attempt < 3 else 60
                        logger.warning(f"{resp.status_code} on proxy, retrying with new proxy in {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"{resp.status_code} persistent after {max_retries} retries")
                
                resp.raise_for_status()
                return resp.text.strip()
                
        except httpx.ProxyError as e:
            logger.warning(f"Proxy failed: {proxy_config['http://'][:30]}... | {e}")
            # Try next retry with different proxy (random.choice handles this)
            if attempt < max_retries:
                await asyncio.sleep(5)
                continue
            raise
            
        except httpx.TimeoutException:
            if attempt < max_retries:
                await asyncio.sleep(10)
                continue
            raise
            
        except httpx.RequestError as e:
            if attempt < max_retries:
                await asyncio.sleep(5)
                continue
            raise
    
    raise RuntimeError(f"Failed to fetch {clean_url} after {max_retries} retries")
