import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from groq import AsyncGroq

from config.settings import GROQ_API_KEY_SCRAPER, SCRAPER_MODEL, REQUEST_DELAY
from core.scraper_client import fetch_url
from core.models import AgentProfile

logger = logging.getLogger(__name__)

# Max chars sent to the LLM — keeps prompts inside context window
LIST_PAGE_LIMIT = 8_000
PROFILE_PAGE_LIMIT = 12_000


class ScraperAgent:
    """
    The Scraper Agent uses Jina AI to fetch Zillow pages and an LLM
    to extract structured data from the raw markdown.
    """

    def __init__(self):
        self.client = AsyncGroq(api_key=GROQ_API_KEY_SCRAPER)
        self.model = SCRAPER_MODEL

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    async def scrape_agents(self, instructions: dict) -> List[AgentProfile]:
        search_urls: List[str] = instructions.get("zillow_search_urls", [])
        fields: List[str] = instructions.get("fields_to_extract", [])
        max_agents: int = instructions.get("max_agents", 50)

        logger.info(f"Scraper → {len(search_urls)} search pages | max {max_agents} agents")

        # --- Phase 1: collect profile links ---
        profile_links: List[str] = []
        for url in search_urls:
            if len(profile_links) >= max_agents:
                break
            links = await self._extract_profile_links(url)
            for link in links:
                if link not in profile_links:
                    profile_links.append(link)
            await asyncio.sleep(REQUEST_DELAY)

        profile_links = profile_links[:max_agents]
        logger.info(f"Scraper → {len(profile_links)} unique profile links found")
        self._checkpoint({"profile_links": profile_links}, "phase1_links")

        # --- Phase 2: scrape each profile ---
        agents: List[AgentProfile] = []
        for idx, link in enumerate(profile_links, 1):
            logger.info(f"Scraper → profile {idx}/{len(profile_links)}: {link}")
            agent = await self._scrape_profile(link, fields)
            if agent:
                agents.append(agent)
            await asyncio.sleep(REQUEST_DELAY)

        self._checkpoint(
            {"agents": [a.model_dump() for a in agents]}, "phase2_profiles"
        )
        logger.info(f"Scraper → done. {len(agents)} profiles scraped successfully.")
        return agents

    # ------------------------------------------------------------------ #
    #  Phase 1 helpers                                                     #
    # ------------------------------------------------------------------ #

  import re

async def _extract_profile_links(self, search_url: str) -> List[str]:
    try:
        raw = await fetch_url(search_url)

        # ── Step 1: Extract /profile/ links with regex (fast, reliable) ──
        found = re.findall(
            r'https?://(?:www\.)?zillow\.com/profile/[^/"\'>\s]+',
            raw
        )
        # Also catch relative URLs
        found += [
            f"https://www.zillow.com{m}"
            for m in re.findall(r'"/profile/[^"\'>\s]+', raw)
        ]

        # Clean and deduplicate
        clean = []
        for link in found:
            link = link.strip('",\'').rstrip("/") + "/"
            if "zillow.com/profile/" in link and link not in clean:
                clean.append(link)

        if clean:
            logger.info(f"Scraper → {len(clean)} links from {search_url}")
            return clean

        # ── Step 2: Fallback to LLM only if regex found nothing ──
        logger.warning(f"Scraper → regex found 0 links, trying LLM fallback for {search_url}")
        content = raw[:LIST_PAGE_LIMIT]

        prompt = f"""Extract all Zillow agent profile URLs from this HTML.
Profile URLs follow this pattern: https://www.zillow.com/profile/AgentName/

HTML:
{content}

Return ONLY valid JSON:
{{"profile_urls": ["https://www.zillow.com/profile/...", ...]}}

If you find none, return {{"profile_urls": []}}"""

        text = await self._chat(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=1500,
        )

        data = json.loads(text)
        raw_links: List[str] = data.get("profile_urls", [])

        for link in raw_links:
            if link.startswith("/profile/"):
                link = f"https://www.zillow.com{link}"
            link = link.rstrip("/") + "/"
            if "zillow.com/profile/" in link and link not in clean:
                clean.append(link)

        logger.info(f"Scraper → {len(clean)} links (via LLM) from {search_url}")
        return clean

    except Exception as exc:
        logger.error(f"Scraper → failed on {search_url}: {exc}")
        return []
    # ------------------------------------------------------------------ #
    #  Phase 2 helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _scrape_profile(
        self, profile_url: str, fields: List[str]
    ) -> Optional[AgentProfile]:
        try:
            raw = await fetch_url(profile_url)
            content = raw[:PROFILE_PAGE_LIMIT]

            prompt = f"""You are parsing a Zillow real estate agent profile page (rendered as markdown).

Profile URL: {profile_url}
Fields the business owner wants: {fields}

Content:
{content}

Extract all available data and return ONLY this JSON (use null for missing fields):
{{
  "name": "Full name",
  "location": "City, State",
  "rating": 4.8,
  "review_count": 42,
  "years_experience": 7,
  "recent_sales": 15,
  "brokerage": "RE/MAX ...",
  "specialties": ["Buyer's Agent", "Listing Agent"],
  "languages": ["English"],
  "about": "Bio text (max 500 chars)",
  "phone": "305-555-0100 or null",
  "email": "agent@email.com or null"
}}"""

            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=800,
            )

            data = json.loads(resp.choices[0].message.content)
            data["profile_url"] = profile_url
            data["scraped_at"] = datetime.utcnow().isoformat()

            # Trim about field
            if data.get("about") and len(data["about"]) > 500:
                data["about"] = data["about"][:500]

            # Build model safely — ignore unknown keys
            known = set(AgentProfile.model_fields.keys())
            filtered = {k: v for k, v in data.items() if k in known}
            return AgentProfile(**filtered)

        except Exception as exc:
            logger.error(f"Scraper → failed on {profile_url}: {exc}")
            return None

    # ------------------------------------------------------------------ #
    #  Checkpointing                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _checkpoint(data: dict, name: str) -> None:
        path = Path(f"data/leads/checkpoint_{name}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Checkpoint saved → {path}")
