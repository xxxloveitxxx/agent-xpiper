# core/scraper_client.py
import re
import httpx
import asyncio
import logging
import random

logger = logging.getLogger(__name__)
TIMEOUT = 60

# Pool of free markdown converters — rotated per request
CONVERTERS = [
    "jina",
    "urltomarkdown",
]

def _sanitize_zillow_url(url: str) -> str:
    clean = re.sub(r'[)/]+$', '', url)
    if not clean.startswith('http'):
        clean = 'https://' + clean.lstrip('/')
    return clean

def _is_profile_url(url: str) -> bool:
    return "/profile/" in url

async def _fetch_via_jina(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Jina GET with headers that request fresh fetch."""
    return await client.get(
        f"https://r.jina.ai/{url}",
        headers={
            "Accept": "text/plain",
            "X-No-Cache": "true",           # force fresh, don't serve cached blocked page
            "X-With-Links-Summary": "true", # include links
            "X-Timeout": "25",
        }
    )

async def _fetch_via_jina_post(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Jina POST — different code path on their end, sometimes bypasses blocks."""
    return await client.post(
        "https://r.jina.ai/",
        headers={
            "Accept": "text/plain",
            "Content-Type": "application/json",
            "X-No-Cache": "true",
        },
        json={"url": url}
    )

async def _fetch_via_urltomarkdown(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Heroku instance — works for list pages, sometimes profiles too."""
    return await client.get(
        "https://urltomarkdown.herokuapp.com/",
        params={"url": url, "clean": "false", "links": "true", "title": "false"},
        headers={"Accept": "text/plain"}
    )

# Ordered strategy per URL type
PROFILE_STRATEGIES = [_fetch_via_jina, _fetch_via_jina_post, _fetch_via_urltomarkdown]
LIST_STRATEGIES    = [_fetch_via_urltomarkdown, _fetch_via_jina, _fetch_via_jina_post]

async def fetch_url(url: str, max_retries: int = 3) -> str:
    clean_url = _sanitize_zillow_url(url)
    strategies = PROFILE_STRATEGIES if _is_profile_url(clean_url) else LIST_STRATEGIES

    for attempt, strategy in enumerate(strategies):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                logger.info(f"fetch_url → attempt {attempt+1} via {strategy.__name__} for {clean_url}")
                resp = await strategy(client, clean_url)

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 30))
                    logger.warning(f"429 from {strategy.__name__}. Waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code in (502, 503, 504):
                    wait = 10 * (attempt + 1)
                    logger.warning(f"{resp.status_code} from {strategy.__name__}. Waiting {wait}s, trying next strategy...")
                    await asyncio.sleep(wait)
                    continue

                # Zillow denied — Jina fetched OK but got a block page
                if resp.status_code == 200 and any(
                    phrase in resp.text[:500].lower()
                    for phrase in ["access denied", "robot", "captcha", "blocked", "unusual traffic"]
                ):
                    logger.warning(f"{strategy.__name__} got Zillow block page, trying next strategy...")
                    await asyncio.sleep(5)
                    continue

                resp.raise_for_status()
                return resp.text.strip()

        except httpx.TimeoutException:
            logger.warning(f"Timeout on {strategy.__name__}, trying next...")
            await asyncio.sleep(5)
            continue

        except httpx.RequestError as e:
            logger.warning(f"Request error on {strategy.__name__}: {e}, trying next...")
            await asyncio.sleep(5)
            continue

    raise RuntimeError(f"All strategies failed for {clean_url}")
