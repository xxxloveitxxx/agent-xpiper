# agents/scraper.py — REPLACE the entire _scrape_profile method

import re
from datetime import datetime
from typing import Optional
from core.models import AgentProfile


# agents/scraper.py — TOP OF FILE (first 10 lines)
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional  # ← ADD THIS LINE

from config.settings import GROQ_API_KEY_SCRAPER, SCRAPER_MODEL, REQUEST_DELAY, GROQ_MODELS
from core.llm_client import make_client, chat_with_fallback
from core.models import AgentProfile


class ScraperAgent:  # ← CLASS DEFINITION MUST BE HERE

#    def __init__(self):
 #       self._chat = make_client(api_key, SCRAPER_MODEL)

async def scraperagent(self, profile_url: str, fields: List[str]) -> Optional[AgentProfile]:
    """
    Extract agent data using regex patterns instead of LLM.
    Faster, free, and deterministic.
    """
    try:
        from core.scraper_client import fetch_url
        raw = await fetch_url(profile_url)
        content = raw[:PROFILE_PAGE_LIMIT]
        
        # === REGEX EXTRACTION FUNCTIONS ===
        
        def extract_name(md: str) -> Optional[str]:
            # Pattern: # Name or **Name** at top of profile
            match = re.search(r'^#\s+([A-Z][^#\n]+?)(?:\n|$)', md, re.MULTILINE)
            if match:
                return match.group(1).strip().replace(')/', '')
            # Fallback: bold name
            match = re.search(r'\*\*([A-Z][^*]{2,50}?)\*\*', md)
            if match:
                return match.group(1).strip()
            return None

        def extract_location(md: str) -> Optional[str]:
            # Pattern: "City, State" near top
            match = re.search(r'([A-Z][a-z]+,\s*[A-Z]{2})(?:\s*[-•]|$)', md)
            if match:
                return match.group(1).strip()
            return None

        def extract_brokerage(md: str) -> Optional[str]:
            # Pattern: "at Brokerage Name" or "with Brokerage"
            match = re.search(r'(?:at|with|@)\s+([A-Z][^,\n•|]{3,60}?(?:Real(?:ty|Estate)?|Group|LLC|Inc\.?))', md, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            # Fallback: line after "Brokerage:"
            match = re.search(r'Brokerage[:\s]+([^\n]+)', md, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            return None

        def extract_rating(md: str) -> Optional[float]:
            # Pattern: "4.8" or "4.8 out of 5" or "★ 4.8"
            match = re.search(r'(?:★|rating[:\s]*)?(\d\.\d)\s*(?:out\s+of\s+5)?', md, re.IGNORECASE)
            if match:
                return float(match.group(1))
            return None

        def extract_reviews(md: str) -> Optional[int]:
            # Pattern: "123 reviews" or "(456)"
            match = re.search(r'\((\d{1,4})\s*reviews?\)', md, re.IGNORECASE)
            if match:
                return int(match.group(1))
            match = re.search(r'(\d{1,4})\s+reviews?', md, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return None

        def extract_years_experience(md: str) -> Optional[int]:
            # Pattern: "14 years" or "14 years experience"
            match = re.search(r'(\d{1,2})\s+years?(?:\s+experience)?', md, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return None

        def extract_recent_sales(md: str) -> Optional[int]:
            # Pattern: "150 sales" or "Recent sales: 150"
            match = re.search(r'(?:recent\s+)?sales?[:\s]+(\d{1,4})', md, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return None

        def extract_specialties(md: str) -> List[str]:
            # Pattern: "Specialties: Buyer's Agent, Listing Agent"
            match = re.search(r'Specialties?[:\s]+([^\n]+)', md, re.IGNORECASE)
            if match:
                raw_specs = match.group(1).strip()
                # Split by comma or pipe
                specs = re.split(r'[,|]', raw_specs)
                return [s.strip() for s in specs if len(s.strip()) > 2][:10]
            return []

        def extract_languages(md: str) -> List[str]:
            # Pattern: "Languages: English, Spanish"
            match = re.search(r'Languages?[:\s]+([^\n]+)', md, re.IGNORECASE)
            if match:
                raw_langs = match.group(1).strip()
                langs = re.split(r'[,|]', raw_langs)
                return [l.strip() for l in langs if len(l.strip()) > 2][:5]
            return []

        def extract_phone(md: str) -> Optional[str]:
            # Pattern: (303) 555-1234 or 303-555-1234 or +1 303 555 1234
            match = re.search(r'(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})', md)
            if match:
                return match.group(1).strip()
            return None

        def extract_email(md: str) -> Optional[str]:
            # Pattern: [text](mailto:email@domain.com)
            match = re.search(r'\[.*?\]\(mailto:([^)]+)\)', md, re.IGNORECASE)
            if match:
                return match.group(1).strip().lower()
            # Fallback: plain email
            match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', md)
            if match:
                return match.group(0).strip().lower()
            return None

        def extract_about(md: str) -> Optional[str]:
            # Pattern: text after "About" heading until next heading or end
            match = re.search(r'##?\s+About[^\n]*\n(.*?)(?:\n##|\Z)', md, re.DOTALL | re.IGNORECASE)
            if match:
                about = re.sub(r'\n+', ' ', match.group(1).strip())
                return about[:500]  # Truncate to 500 chars
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
