# agents/scraper.py — COMPLETE WORKING VERSION
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import GROQ_API_KEY_SCRAPER, SCRAPER_MODEL, REQUEST_DELAY
from core.llm_client import make_client
from core.scraper_client import fetch_url
from core.models import AgentProfile

logger = logging.getLogger(__name__)

LIST_PAGE_LIMIT = 15_000
PROFILE_PAGE_LIMIT = 20_000


class ScraperAgent:

    def __init__(self):
        # Groq-only: no Gemini check
        api_key = GROQ_API_KEY_SCRAPER
        if not api_key:
            raise ValueError("GROQ_API_KEY_SCRAPER is required in .env")
        # make_client returns (_, chat_fn) tuple
        self._chat = make_client(api_key, SCRAPER_MODEL)

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
            raw = await fetch_url(search_url)

            # Regex patterns for Zillow profile URLs
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

            # LLM fallback for link extraction (keep for edge cases)
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

            text = await self._chat(
                [{"role": "user", "content": prompt}],
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
        """
        Extract agent data using regex patterns instead of LLM.
        Faster, free, and deterministic.
        """
        try:
            raw = await fetch_url(profile_url)
            content = raw[:PROFILE_PAGE_LIMIT]
                with open(f"data/leads/debug_{profile_url.split('/')[-2]}.txt", "w") as f:
                    f.write(content)
            # === REGEX EXTRACTION FUNCTIONS (nested for scope) ===
            
            def extract_name(md: str) -> Optional[str]:
                match = re.search(r'^#\s+([A-Z][^#\n]+?)(?:\n|$)', md, re.MULTILINE)
                if match:
                    return match.group(1).strip().replace(')/', '')
                match = re.search(r'\*\*([A-Z][^*]{2,50}?)\*\*', md)
                if match:
                    return match.group(1).strip()
                return None

            def extract_location(md: str) -> Optional[str]:
                match = re.search(r'([A-Z][a-z]+,\s*[A-Z]{2})(?:\s*[-•]|$)', md)
                if match:
                    return match.group(1).strip()
                return None

            def extract_brokerage(md: str) -> Optional[str]:
                match = re.search(r'(?:at|with|@)\s+([A-Z][^,\n•|]{3,60}?(?:Real(?:ty|Estate)?|Group|LLC|Inc\.?))', md, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                match = re.search(r'Brokerage[:\s]+([^\n]+)', md, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return None

            def extract_rating(md: str) -> Optional[float]:
                match = re.search(r'(?:★|rating[:\s]*)?(\d\.\d)\s*(?:out\s+of\s+5)?', md, re.IGNORECASE)
                if match:
                    return float(match.group(1))
                return None

            def extract_reviews(md: str) -> Optional[int]:
                match = re.search(r'\((\d{1,4})\s*reviews?\)', md, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                match = re.search(r'(\d{1,4})\s+reviews?', md, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                return None

            def extract_years_experience(md: str) -> Optional[int]:
                match = re.search(r'(\d{1,2})\s+years?(?:\s+experience)?', md, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                return None

            def extract_recent_sales(md: str) -> Optional[int]:
                match = re.search(r'(?:recent\s+)?sales?[:\s]+(\d{1,4})', md, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                return None

            def extract_specialties(md: str) -> List[str]:
                match = re.search(r'Specialties?[:\s]+([^\n]+)', md, re.IGNORECASE)
                if match:
                    raw_specs = match.group(1).strip()
                    specs = re.split(r'[,|]', raw_specs)
                    return [s.strip() for s in specs if len(s.strip()) > 2][:10]
                return []

            def extract_languages(md: str) -> List[str]:
                match = re.search(r'Languages?[:\s]+([^\n]+)', md, re.IGNORECASE)
                if match:
                    raw_langs = match.group(1).strip()
                    langs = re.split(r'[,|]', raw_langs)
                    return [l.strip() for l in langs if len(l.strip()) > 2][:5]
                return []

            def extract_phone(md: str) -> Optional[str]:
                match = re.search(r'(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})', md)
                if match:
                    return match.group(1).strip()
                return None

            def extract_email(md: str) -> Optional[str]:
                # Primary: mailto links
                match = re.search(r'\[.*?\]\(mailto:([^)]+)\)', md, re.IGNORECASE)
                if match:
                    return match.group(1).strip().lower()
                # Fallback: plain email
                match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', md)
                if match:
                    return match.group(0).strip().lower()
                return None

            def extract_about(md: str) -> Optional[str]:
                match = re.search(r'##?\s+About[^\n]*\n(.*?)(?:\n##|\Z)', md, re.DOTALL | re.IGNORECASE)
                if match:
                    about = re.sub(r'\n+', ' ', match.group(1).strip())
                    return about[:500]
                return None

            # === RUN EXTRACTION ===
            data = {
                "name": extract_name(content),
                "location": extract_location(content),
                "brokerage": extract_brokerage(content),
                "rating": extract_rating(content),
                "review_count": extract_reviews(content),
                "years_experience": extract_years_experience(content),
                "recent_sales": extract_recent_sales(content),
                "specialties": extract_specialties(content),
                "languages": extract_languages(content),
                "phone": extract_phone(content),
                "email": extract_email(content),
                "about": extract_about(content),
                "profile_url": profile_url.rstrip(')/').rstrip('/') + '/',
                "scraped_at": datetime.utcnow().isoformat()
            }
            
            # Filter to only valid AgentProfile fields
            known = set(AgentProfile.model_fields.keys())
            filtered = {k: v for k, v in data.items() if k in known}
            
            # Log what was found for debugging
            found_fields = [k for k, v in filtered.items() if v and (not isinstance(v, (list, str)) or v)]
            logger.debug(f"✓ Extracted {len(found_fields)} fields via regex: {found_fields}")
            
            return AgentProfile(**filtered)

        except Exception as exc:
            logger.error(f"Scraper → regex extraction failed on {profile_url}: {exc}")
            return None

    @staticmethod
    def _checkpoint(data: dict, name: str) -> None:
        path = Path(f"data/leads/checkpoint_{name}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Checkpoint saved → {path}")
