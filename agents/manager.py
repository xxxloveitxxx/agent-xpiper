# agents/manager.py
import json
import logging
from pathlib import Path
from typing import List

from config.settings import (
    GROQ_API_KEY_MANAGER, MANAGER_MODEL, GROQ_MODELS
)
from core.llm_client import make_client
from core.models import AgentProfile

logger = logging.getLogger(__name__)


class ManagerAgent:

    def __init__(self):
        api_key = GROQ_API_KEY_MANAGER
        self._client = make_client(api_key, MANAGER_MODEL)
        self._model_chain = GROQ_MODELS.get("manager", [MANAGER_MODEL])

    def load_criteria(self, criteria_file: str = "config/criteria.json") -> dict:
        path = Path(criteria_file)
        if not path.exists():
            logger.warning(f"Criteria file not found: {path}, using defaults")
            return self._default_criteria()
        with open(path, "r") as f:
            criteria = json.load(f)
        logger.info(f"✓ Criteria loaded for: {criteria.get('campaign_name', 'Unknown')}")
        return criteria

    @staticmethod
    def _default_criteria() -> dict:
        return {
            "campaign_name": "Default Campaign",
            "target_locations": ["Denver, CO"],
            "min_rating": 4.5,
            "min_reviews": 20,
            "min_experience_years": 3,
            "min_recent_sales": 10,
            "preferred_specialties": ["Buyer's Agent", "Listing Agent"],
            "exclude_brokerages": [],
            "max_agents_to_scrape": 50,
            "fields_to_extract": [
                "name", "location", "brokerage", "rating", "review_count",
                "years_experience", "recent_sales", "specialties", "languages",
                "phone", "email", "about"
            ]
        }

    async def generate_scraping_instructions(self, criteria: dict) -> dict:
        logger.info("Manager → generating scraping plan...")

        target_locations = criteria.get("target_locations", ["Denver, CO"])
        max_agents = criteria.get("max_agents_to_scrape", 50)

        # Calculate pages needed — Zillow shows ~15 agents per page, cap at 5 pages
        pages_needed = max(1, -(-max_agents // 15))  # ceiling division
        pages_needed = min(pages_needed, 5)

        search_urls = []
        for loc in target_locations:
            slug = loc.lower().replace(", ", "-").replace(" ", "-")
            for page in range(1, pages_needed + 1):
                search_urls.append(
                    f"https://www.zillow.com/professionals/real-estate-agent-reviews/{slug}/?page={page}"
                )

        plan = {
            "zillow_search_urls": search_urls,
            "fields_to_extract": criteria.get("fields_to_extract", [
                "name", "location", "brokerage", "rating", "review_count",
                "years_experience", "recent_sales", "specialties", "languages",
                "phone", "email", "about"
            ]),
            "max_agents": max_agents,
        }

        logger.info(f"Manager → plan ready: {len(plan['zillow_search_urls'])} URLs")
        return plan

    @staticmethod
    def _summarize_agents(agents: List[AgentProfile]) -> dict:
        if not agents:
            return {"count": 0}

        ratings = [a.rating for a in agents if a.rating]
        reviews = [a.review_count for a in agents if a.review_count]
        brokerages = [a.brokerage for a in agents if a.brokerage]
        specialties = [s for a in agents if a.specialties for s in a.specialties]

        return {
            "count": len(agents),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "avg_reviews": round(sum(reviews) / len(reviews)) if reviews else None,
            "top_brokerages": list(set(brokerages))[:5],
            "common_specialties": list(set(specialties))[:10],
        }
