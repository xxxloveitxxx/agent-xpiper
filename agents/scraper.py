# agents/scraper.py
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import (
    GROQ_API_KEY_SCRAPER, GEMINI_API_KEY, PROVIDER, SCRAPER_MODEL, REQUEST_DELAY, GROQ_MODELS
)
from core.llm_client import make_client, chat_with_fallback
from core.models import AgentProfile

logger = logging.getLogger(__name__)

LIST_PAGE_LIMIT = 15_000
PROFILE_PAGE_LIMIT = 20_000


class ScraperAgent:

    def __init__(self):
        api_key = GEMINI_API_KEY if PROVIDER == "gemini" else GROQ_API_KEY_SCRAPER
        self._client, _ = make_client(api_key, SCRAPER_MODEL)
        self._model_chain = GROQ_MODELS.get("scraper", [SCRAPER_MODEL])

    async def scrape_agents(self, instructions: dict) -> List[AgentProfile]:
        search_urls: List[str] = instructions.get("zillow_search_urls", [])
        fields: List[str] = instructions.get("fields_to_extract", [])
        max_agents: int = instructions.get("max_agents", 50)

        logger.info(f"Scraper → {len(search_urls)} search pages | max {max_agents} agents")

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

        if not profile_links:
            logger.warning("Scraper → no profile links found across all search pages")
            return []

        agents: List[AgentProfile] = []
        for idx, link in enumerate(profile_links, 1):
            logger.info(f"Scraper → profile {idx}/{len(profile_links)}: {link}")
            agent = await self._scrape_profile(link, fields)
            if agent:
                agents.append(agent)
            await asyncio.sleep(REQUEST_DELAY)

        self._checkpoint({"agents": [a.model_dump() for a in agents]}, "phase2_profiles")
        logger.info(f"Scraper → done. {len(agents)} profiles scraped successfully.")
        return agents

    async def _extract_profile_links(self, search_url: str) -> List[str]:
        try:
            from core.scraper_client import fetch_url
            raw = await fetch_url(search_url)

            found = re.findall(
                r'https?://(?:www\.)?zillow\.com/profile/[^/"\'>\s]+',
                raw
            )
            found += re.findall(
                r'https?://(?:www\.)?zillow\.com/professionals/[^/"\'>\s]+-agent/[^/"\'>\s]+',
                raw
            )
            base = "https://www.zillow.com"
            found += [
                base + m.strip("\"'")
                for m in re.findall(r'["\'](/profile/[^"\'>\s]+)', raw)
            ]
            found += [
                base + m.strip("\"'")
                for m in re.findall(r'["\'](/professionals/[^"\'>\s]+-agent/[^"\'>\s]+)', raw)
            ]

            clean = []
            for link in found:
                link = link.strip('",\' ').rstrip("/") + "/"
                if "zillow.com/" in link and link not in clean:
                    clean.append(link)

            if clean:
                logger.info(f"Scraper → {len(clean)} links from {search_url}")
                return clean

            logger.warning(f"Scraper → regex found 0 links, trying LLM fallback for {search_url}")
            content = raw[:LIST_PAGE_LIMIT]

            prompt = f"""Extract all Zillow agent profile URLs from this markdown page.
Profile URLs follow these patterns:
- https://www.zillow.com/profile/AgentName/
- https://www.zillow.com/professionals/real-estate-agent-reviews/agent-name-id/

Markdown:
{content}

Return ONLY valid JSON:
{{"profile_urls": ["https://www.zillow.com/profile/...", ...]}}

If none found return {{"profile_urls": []}}"""

            text = await chat_with_fallback(
                client=self._client,
                messages=[{"role": "user", "content": prompt}],
                model_chain=self._model_chain,
                json_mode=True,
                max_tokens=1500,
            )

            data = json.loads(text)
            for link in data.get("profile_urls", []):
                if link.startswith("/profile/") or link.startswith("/professionals/"):
                    link = f"https://www.zillow.com{link}"
                link = link.rstrip("/") + "/"
                if "zillow.com/" in link and link not in clean:
                    clean.append(link)

            logger.info(f"Scraper → {len(clean)} links (LLM fallback) from {search_url}")
            return clean

        except Exception as exc:
            logger.error(f"Scraper → failed on {search_url}: {exc}")
            return []

    async def _scrape_profile(self, profile_url: str, fields: List[str]) -> Optional[AgentProfile]:
        try:
            from core.scraper_client import fetch_url
            raw = await fetch_url(profile_url)
            content = raw[:PROFILE_PAGE_LIMIT]

            prompt = f"""You are parsing a Zillow real estate agent profile page in MARKDOWN format.

Profile URL: {profile_url}
Fields to extract: {fields}

=== CRITICAL: EMAIL EXTRACTION FROM MARKDOWN ===
Emails appear in mailto links like this:
  [clientcare+broker@8z.com](mailto:clientcare+broker@8z.com)
  [Contact Agent](mailto:dave.ness@thriverealestate.com)

To extract emails:
1. Find patterns: [any text](mailto:EMAIL_HERE)
2. Extract ONLY the email inside mailto: (ignore the link text like "Contact")
3. Remove the "mailto:" prefix — return clean email only
4. If multiple emails exist, return the primary contact email
5. If no mailto link, check for plain text: agent@brokerage.com
6. If no email found anywhere, return null

=== OUTPUT JSON SCHEMA (STRICT) ===
{{
  "name": "Full name or team name",
  "location": "City, State",
  "rating": 4.8,
  "review_count": 42,
  "years_experience": 7,
  "recent_sales": 15,
  "brokerage": "Brokerage name",
  "specialties": ["Buyer's Agent", "Listing Agent"],
  "languages": ["English", "Spanish"],
  "about": "Bio text, max 500 characters",
  "phone": "305-555-0100 or null",
  "email": "clientcare+broker@8z.com or null"
}}

=== RULES ===
- Return VALID JSON only, no markdown, no explanations
- Use null (not "null" string) for missing fields
- Keep "about" under 500 chars
- Specialties/languages as arrays, not comma strings
- Email must be clean: no "mailto:", no link text

Markdown content:
{content}"""

            text = await chat_with_fallback(
                client=self._client,
                messages=[{"role": "user", "content": prompt}],
                model_chain=self._model_chain,
                json_mode=True,
                max_tokens=800,
            )

            data = json.loads(text)
            data["profile_url"] = profile_url
            data["scraped_at"] = datetime.utcnow().isoformat()

            for field in ("specialties", "languages"):
                val = data.get(field)
                if val is None:
                    data[field] = []
                elif isinstance(val, str):
                    data[field] = [v.strip() for v in val.split(",") if v.strip()]

            if data.get("about") and len(data["about"]) > 500:
                data["about"] = data["about"][:500]

            known = set(AgentProfile.model_fields.keys())
            filtered = {k: v for k, v in data.items() if k in known}
            return AgentProfile(**filtered)

        except Exception as exc:
            logger.error(f"Scraper → failed on {profile_url}: {exc}")
            return None

    @staticmethod
    def _checkpoint(data: dict, name: str) -> None:
        path = Path(f"data/leads/checkpoint_{name}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Checkpoint saved → {path}")
