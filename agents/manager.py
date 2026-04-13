# agents/manager.py
import json
import logging
from pathlib import Path
from typing import List

from config.settings import GROQ_API_KEY_MANAGER, MANAGER_MODEL, GROQ_MODELS
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

        # ── City cycling from config/cities.json ──────────────────────
        cities_path  = Path("config/cities.json")
        scraped_path = Path("data/leads/scraped_cities.json")

        if cities_path.exists():
            with open(cities_path, "r") as f:
                all_cities = json.load(f)

            # Load already-scraped cities
            scraped: List[str] = []
            if scraped_path.exists():
                with open(scraped_path, "r") as f:
                    scraped = json.load(f)

            remaining = [c for c in all_cities if c not in scraped]

            # Full cycle complete — reset
            if not remaining:
                logger.info("All cities scraped — resetting cycle")
                scraped    = []
                remaining  = all_cities
                scraped_path.parent.mkdir(parents=True, exist_ok=True)
                scraped_path.write_text("[]")

            # How many cities per run (default 1)
            batch_size = criteria.get("scraping_config", {}).get("cities_per_run", 1)
            batch      = remaining[:batch_size]

            criteria.setdefault("target_market", {})["locations"] = batch
            logger.info(
                f"Cities this run: {batch} "
                f"({len(remaining) - len(batch)} remaining in cycle)"
            )
        # ──────────────────────────────────────────────────────────────

        name = criteria.get("business_info", {}).get("name", "Unknown")
        logger.info(f"✓ Criteria loaded for: {name}")
        return criteria

    @staticmethod
    def _default_criteria() -> dict:
        return {
            "business_info": {"name": "Default Campaign"},
            "target_market": {
                "locations": ["Denver, CO"],
                "agent_type": "any",
            },
            "qualification_criteria": {
                "min_reviews": 0,
                "min_rating": 0,
                "min_years_experience": 1,
                "min_recent_sales": 3,
            },
            "scraping_config": {
                "max_pages":      3,
                "max_agents":     50,
                "cities_per_run": 1,
            },
        }

    async def generate_scraping_instructions(self, criteria: dict) -> dict:
        logger.info("Manager → generating scraping plan...")

        locations  = criteria.get("target_market", {}).get("locations", ["Denver, CO"])
        max_agents = criteria.get("scraping_config", {}).get("max_agents", 50)
        max_pages  = criteria.get("scraping_config", {}).get("max_pages", 3)

        search_urls = []
        for loc in locations:
            slug = loc.lower().strip().replace(", ", "-").replace(" ", "-")
            for page in range(1, max_pages + 1):
                search_urls.append(
                    f"https://www.zillow.com/professionals/real-estate-agent-reviews/{slug}/?page={page}"
                )

        plan = {
            "zillow_search_urls": search_urls,
            "fields_to_extract": [
                "name", "location", "brokerage", "rating", "review_count",
                "years_experience", "recent_sales", "specialties", "languages",
                "phone", "email", "about",
            ],
            "max_agents": max_agents,
        }

        logger.info(f"Manager → plan ready: {len(plan['zillow_search_urls'])} URLs")
        return plan

    @staticmethod
    def _summarize_agents(agents: List[AgentProfile]) -> dict:
        if not agents:
            return {"count": 0}

        ratings     = [a.rating for a in agents if a.rating]
        reviews     = [a.review_count for a in agents if a.review_count]
        brokerages  = [a.brokerage for a in agents if a.brokerage]
        specialties = [s for a in agents if a.specialties for s in a.specialties]

        return {
            "count":              len(agents),
            "avg_rating":         round(sum(ratings) / len(ratings), 2) if ratings else None,
            "avg_reviews":        round(sum(reviews) / len(reviews)) if reviews else None,
            "top_brokerages":     list(set(brokerages))[:5],
            "common_specialties": list(set(specialties))[:10],
        }
