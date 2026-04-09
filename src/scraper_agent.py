# core/scraper_client.py
import httpx
import asyncio
import logging
from core.proxy_manager import WebshareProxyManager

logger = logging.getLogger(__name__)

# Initialize proxy manager (call once at app startup)
proxy_manager = None

def init_proxies(webshare_api_key: str):
    global proxy_manager
    proxy_manager = WebshareProxyManager(api_key=webshare_api_key)

async def fetch_url(url: str, max_retries: int = 2, use_proxy: bool = True) -> str:
    """
    Fetch Zillow profile markdown, with optional Webshare proxy rotation.
    """
    clean_url = url.rstrip(')/').rstrip('/')
    if not clean_url.startswith('http'):
        clean_url = 'https://' + clean_url.lstrip('/')
    
    # Refresh proxies on first use or if empty
    if use_proxy and proxy_manager and not proxy_manager._proxies:
        count = await proxy_manager.refresh()
        logger.info(f"✓ Loaded {count} Webshare proxies")
    
    for attempt in range(max_retries + 1):
        try:
            # Build proxy config
            proxies_config = None
            if use_proxy and proxy_manager:
                proxy_url = proxy_manager.get_next_proxy()
                if proxy_url:
                    proxies_config = {"http://": proxy_url, "https://": proxy_url}
                    logger.debug(f"Using proxy: {proxy_url.split('@')[1]}")  # Hide auth
            
            async with httpx.AsyncClient(
                timeout=35,
                proxies=proxies_config,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.zillow.com/"
                }
            ) as client:
                # Fetch raw HTML from Zillow directly
                resp = await client.get(clean_url, follow_redirects=True)
                
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    logger.warning(f"429 on proxy, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                
                if resp.status_code in [502, 503, 504]:
                    if attempt < max_retries:
                        await asyncio.sleep(15 * (attempt + 1))
                        continue
                    raise
                
                resp.raise_for_status()
                html = resp.text
                
                # Convert HTML → markdown locally (simple fallback)
                # For production: use 'markdownify' or 'trafilatura' libraries
                markdown = _html_to_markdown_simple(html)
                return markdown.strip()
                
        except httpx.ProxyError as e:
            logger.warning(f"Proxy failed, rotating: {e}")
            if attempt < max_retries:
                await asyncio.sleep(5)
                continue
            raise
        except httpx.RequestError as e:
            if attempt < max_retries:
                await asyncio.sleep(10)
                continue
            raise
    
    raise RuntimeError(f"Failed to fetch {clean_url} after {max_retries} retries")


def _html_to_markdown_simple(html: str) -> str:
    """
    Minimal HTML → markdown converter.
    For production: pip install markdownify and use:
        from markdownify import markdownify as md
        return md(html)
    """
    # Remove scripts/styles
    import re
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Basic conversions
    html = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n## \1\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'[\2](\1)', html, flags=re.IGNORECASE)
    html = re.sub(r'<[^>]+>', '', html)  # Remove remaining tags
    
    # Clean whitespace
    return re.sub(r'\n{3,}', '\n\n', html).strip()
