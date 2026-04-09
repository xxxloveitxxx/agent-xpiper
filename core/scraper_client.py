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

# === Add this near the top of core/scraper_client.py, after imports ===

# Global proxy manager instance (initialized by init_proxies)
_proxy_manager = None


def init_proxies(webshare_api_key: str, proxy_count: int = 10):
    """
    Initialize Webshare.io proxy rotation for scraper requests.
    
    Call this once at app startup:
        from core.scraper_client import init_proxies
        init_proxies(os.getenv("WEBSHARE_API_KEY"))
    
    Args:
        webshare_api_key: Your Webshare.io API token
        proxy_count: Number of proxies to load (default: 10)
    """
    global _proxy_manager
    _proxy_manager = WebshareProxyManager(
        api_key=webshare_api_key,
        proxy_count=proxy_count
    )
    logger.info(f"✓ Webshare proxy manager initialized ({proxy_count} proxies)")


def _get_proxy_for_request() -> Optional[str]:
    """Helper: get next proxy URL for httpx request, or None if disabled."""
    if _proxy_manager and _proxy_manager._proxies:
        return _proxy_manager.get_next_proxy()
    return None
        
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









#************************************************************







# === WebshareProxyManager class (add to scraper_client.py or separate file) ===
import httpx
from typing import List, Optional

class WebshareProxyManager:
    """Rotate Webshare.io HTTP proxies."""
    
    def __init__(self, api_key: str, proxy_count: int = 10):
        self.api_key = api_key
        self.proxy_count = proxy_count
        self._proxies: List[str] = []
        self._index = 0
    
    async def fetch_proxies(self) -> List[str]:
        """Fetch active HTTP proxies from Webshare API."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://proxy.webshare.io/api/v2/proxy/list/",
                headers={"Authorization": f"Token {self.api_key}"},
                params={"page_size": self.proxy_count, "proxy_type": "http"}
            )
            resp.raise_for_status()
            data = resp.json()
            
            proxies = []
            for p in data.get("results", []):
                if p.get("is_active"):
                    auth = f"{p['username']}:{p['password']}@"
                    url = f"http://{auth}{p['proxy_address']}:{p['port']}"
                    proxies.append(url)
            return proxies
    
    def get_next_proxy(self) -> Optional[str]:
        """Return next proxy in rotation."""
        if not self._proxies:
            return None
        proxy = self._proxies[self._index]
        self._index = (self._index + 1) % len(self._proxies)
        return proxy
    
    async def refresh(self) -> int:
        """Refresh proxy list from API. Returns count loaded."""
        self._proxies = await self.fetch_proxies()
        self._index = 0
        return len(self._proxies)
