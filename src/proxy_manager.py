# core/proxy_manager.py
import httpx
import random
import os
from typing import Optional, List

class WebshareProxyManager:
    """Rotate Webshare.io proxies for httpx requests."""
    
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
            
            # Format: "http://username:password@proxy.webshare.io:port"
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
    
    async def refresh(self):
        """Refresh proxy list from API."""
        self._proxies = await self.fetch_proxies()
        self._index = 0
        return len(self._proxies)
