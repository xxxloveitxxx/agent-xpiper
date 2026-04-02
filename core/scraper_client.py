"""
Rotating scraper client — tries scrape.do → WebScrapingAPI → ScrapingAnt
Falls back automatically if one fails or quota runs out.
"""
import httpx
import os
import logging
import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)



TIMEOUT = 45.0


# ── Individual provider functions ──────────────────────────────────────────

def _key_for(name: str) -> bool:
    keys = {
        "scrape.do":      os.getenv("SCRAPEDO_API_KEY", ""),
        "WebScrapingAPI": os.getenv("WEBSCRAPINGAPI_KEY", ""),
        "ScrapingAnt":    os.getenv("SCRAPINGANT_API_KEY", ""),
    }
    return bool(keys.get(name, ""))


async def _fetch_scrapedo(url: str) -> str:
    api_key = os.getenv("SCRAPEDO_API_KEY", "")
    if not api_key:
        raise ValueError("SCRAPEDO_API_KEY not set")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            "https://api.scrape.do",
            params={
                "token": api_key,
                "url": url,
                "render": "true",
                "super": "true",
                "geoCode": "us",
            },
        )
        resp.raise_for_status()
        content = resp.text
    if not content or len(content) < 200:
        raise ValueError(f"scrape.do returned empty content for {url}")
    return content


async def _fetch_webscrapingapi(url: str) -> str:
    api_key = os.getenv("WEBSCRAPINGAPI_KEY", "")
    if not api_key:
        raise ValueError("WEBSCRAPINGAPI_KEY not set")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            "https://api.webscrapingapi.com/v2",
            params={
                "api_key": api_key,
                "url": url,
                "render_js": "1",
                "proxy_type": "residential",
                "country": "us",
                "wait_for_css": ".agent-name",
                "timeout": "30000",
            },
        )
        resp.raise_for_status()
        content = resp.text
    if not content or len(content) < 200:
        raise ValueError(f"WebScrapingAPI returned empty content for {url}")
    return content


async def _fetch_scrapingant(url: str) -> str:
    api_key = os.getenv("SCRAPINGANT_API_KEY", "")
    if not api_key:
        raise ValueError("SCRAPINGANT_API_KEY not set")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            "https://api.scrapingant.com/v2/general",
            params={
                "url": url,
                "browser": "true",
                "proxy_type": "residential",
                "wait_for_selector": ".agent-name",
            },
            headers={"x-api-key": api_key},
        )
        resp.raise_for_status()
        content = resp.text
    if not content or len(content) < 200:
        raise ValueError(f"ScrapingAnt returned empty content for {url}")
    return content

# ── Provider registry & rotation ───────────────────────────────────────────

PROVIDERS = [
    ("scrape.do",        _fetch_scrapedo),
    ("WebScrapingAPI",   _fetch_webscrapingapi),
    ("ScrapingAnt",      _fetch_scrapingant),
]

# Track which providers are currently working to avoid re-trying dead ones
_failed_providers: set = set()


def _get_active_providers():
    active = [(name, fn) for name, fn in PROVIDERS
              if name not in _failed_providers
              and _key_for(name)]
    if not active:
        # Reset and try everything again (quota may have refreshed)
        _failed_providers.clear()
        active = [(name, fn) for name, fn in PROVIDERS if _key_for(name)]
    return active




# ── Public interface ────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=20),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, ValueError)),
)
async def fetch_url(url: str, get_links: bool = False) -> str:
    """
    Fetch a URL using the first available scraping provider.
    Rotates automatically on failure.
    Returns raw HTML (our LLM will parse it — no need for markdown conversion).
    """
    active = _get_active_providers()

    if not active:
        raise RuntimeError(
            "No scraping API keys configured.\n"
            "Set at least one of: SCRAPEDO_API_KEY, WEBSCRAPINGAPI_KEY, SCRAPINGANT_API_KEY"
        )

    # Shuffle so we don't hammer the same provider on every run
    random.shuffle(active)

    last_error = None
    for name, fetch_fn in active:
        try:
            logger.debug(f"[{name}] fetching: {url}")
            content = await fetch_fn(url)
            logger.info(f"[{name}] ✓ {len(content):,} chars from {url[:60]}")
            return content
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                logger.warning(f"[{name}] Auth error ({status}) — marking as unavailable")
                _failed_providers.add(name)
            elif status == 429:
                logger.warning(f"[{name}] Rate limit hit — marking as unavailable temporarily")
                _failed_providers.add(name)
            else:
                logger.warning(f"[{name}] HTTP {status} — trying next provider")
            last_error = e
        except Exception as e:
            logger.warning(f"[{name}] failed ({type(e).__name__}: {e}) — trying next provider")
            last_error = e

    raise RuntimeError(
        f"All scraping providers failed for {url}. Last error: {last_error}"
    )
