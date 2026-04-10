# core/scraper_client.py
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

URLTOMARKDOWN = "https://urltomarkdown.herokuapp.com/"
JINA = "https://r.jina.ai/"
TIMEOUT = 60

def _sanitize_zillow_url(url: str) -> str:
    clean = re.sub(r'[)/]+$', '', url)
    if not clean.startswith('http'):
        clean = 'https://' + clean.lstrip('/')
    return clean

def _is_profile_url(url: str) -> bool:
    """Profile pages need Jina; list/search pages use urltomarkdown."""
    return "/profile/" in url or (
        "/professionals/" in url and not url.rstrip('/').endswith("page=1") 
        and "agent-reviews" not in url
    )

async def fetch_url(url: str, max_retries: int = 3) -> str:
    import re
    clean_url = _sanitize_zillow_url(url)

    if _is_profile_url(clean_url):
        # Jina: just prepend, no params needed
        request_url = JINA + clean_url
        params = None
        headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
    else:
        # urltomarkdown: works fine for list pages
        request_url = URLTOMARKDOWN
        params = {"url": clean_url, "clean": "false", "links": "true", "title": "false"}
        headers = {"Accept": "text/plain"}

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(request_url, params=params, headers=headers)

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 60 * (2 ** attempt)))
                    logger.warning(f"429 Rate limited. Waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code in [502, 503, 504]:
                    wait = [10, 30, 60][attempt] if attempt < 3 else 60
                    logger.warning(f"{resp.status_code} on {'Jina' if _is_profile_url(clean_url) else 'urltomarkdown'}. Waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.text.strip()

        except httpx.TimeoutException:
            wait = 15 * (attempt + 1)
            logger.warning(f"Timeout. Waiting {wait}s before retry...")
            await asyncio.sleep(wait)
            continue

        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
                continue
            logger.error(f"Request failed after {max_retries} attempts: {e}")
            raise

    raise RuntimeError(f"Failed to fetch {clean_url} after {max_retries} retries")
