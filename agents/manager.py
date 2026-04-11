# agents/manager.py
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from config.settings import (
    GROQ_API_KEY_MANAGER, MANAGER_MODEL, PROVIDER, GROQ_MODELS
)
from core.llm_client import make_client, chat_with_fallback
from core.models import AgentProfile

logger = logging.getLogger(__name__)


class ManagerAgent:

    def __init__(self):
        api_key = GROQ_API_KEY_MANAGER
        self._client = make_client(api_key, MANAGER_MODEL)
        self._model_chain = GROQ_MODELS.get("manager", [MANAGER_MODEL])

    def load_criteria(self, criteria_file: str = "data/criteria.json") -> dict:
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
            "zillow_search_urls": [
                "https://www.zillow.com/professionals/real-estate-agent-reviews/denver-co/?page=1"
            ],
            "fields_to_extract": [
                "name", "location", "brokerage", "rating", "review_count",
                "years_experience", "recent_sales", "specialties", "languages",
                "phone", "email", "about"
            ]
        }

    async def generate_scraping_instructions(self, criteria: dict) -> dict:
        logger.info("Manager → generating scraping plan...")
        
        search_urls = criteria.get("zillow_search_urls", [])
        if not search_urls:
            search_urls = [
                f"https://www.zillow.com/professionals/real-estate-agent-reviews/{loc.lower().replace(', ', '-')}/?page=1"
                for loc in criteria.get("target_locations", ["Denver, CO"])
            ]

        prompt = f"""You are a real estate lead generation strategist.

Campaign: {criteria.get('campaign_name', 'Untitled')}
Target locations: {criteria.get('target_locations')}
Min requirements: rating ≥ {criteria.get('min_rating')}, reviews ≥ {criteria.get('min_reviews')}, experience ≥ {criteria.get('min_experience_years')}y

Generate a scraping plan in STRICT JSON format:
{{
  "zillow_search_urls": ["https://...", ...],
  "fields_to_extract": ["name", "email", "phone", ...],
  "max_agents": {criteria.get('max_agents_to_scrape', 5)}
}}

Rules:
- Return ONLY valid JSON, no explanations
- Include 1 Zillow search URLs for the target locations
- fields_to_extract must include: name, brokerage, rating, review_count, email, phone
- max_agents should not exceed {criteria.get('max_agents_to_scrape', 50)}

Criteria JSON:
{json.dumps(criteria, indent=2)}"""

        resp_text = await chat_with_fallback(
            client=self._client,
            messages=[{"role": "user", "content": prompt}],
            model_chain=self._model_chain,
            json_mode=True,
            max_tokens=1500,
            temperature=0.2,
        )
        
        plan = json.loads(resp_text)
        logger.info(f"Manager → plan ready: {len(plan.get('zillow_search_urls', []))} URLs")
        return plan

    async def generate_qualification_rules(self, criteria: dict, agents_summary: dict) -> dict:
        logger.info("Manager → generating qualification rules...")
        
        prompt = f"""You are a real estate lead scoring expert.

Campaign criteria:
{json.dumps({k: v for k, v in criteria.items() if k not in ['zillow_search_urls']}, indent=2)}

Sample agent data summary (from {agents_summary.get('count', 0)} scraped profiles):
- Avg rating: {agents_summary.get('avg_rating', 'N/A')}
- Avg reviews: {agents_summary.get('avg_reviews', 'N/A')}
- Top brokerages: {agents_summary.get('top_brokerages', [])}
- Common specialties: {agents_summary.get('common_specialties', [])}

Generate qualification rules in STRICT JSON format:
{{
  "min_score": 60,
  "scoring_rules": [
    {{"field": "rating", "condition": ">=", "value": 4.5, "points": 20}},
    {{"field": "review_count", "condition": ">=", "value": 50, "points": 15}},
    ...
  ],
  "disqualifiers": [
    {{"field": "brokerage", "condition": "in", "value": ["Bad Brokerage Inc"]}}
  ],
  "bonus_rules": [
    {{"field": "recent_sales", "condition": ">=", "value": 20, "points": 10}}
  ]
}}

Rules:
- Return ONLY valid JSON, no explanations
- min_score should be between 50-80
- Each scoring rule: field, condition (>=, <=, ==, in, contains), value, points (5-25)
- disqualifiers: if ANY match, agent is auto-rejected
- bonus_rules: extra points for exceptional attributes
- Total possible score should be ~100 points

Output JSON only:"""

        resp_text = await chat_with_fallback(
            client=self._client,
            messages=[{"role": "user", "content": prompt}],
            model_chain=self._model_chain,
            json_mode=True,
            max_tokens=2000,
            temperature=0.2,
        )
        
        rules = json.loads(resp_text)
        logger.info(f"Manager → rules ready (min score: {rules.get('min_score', 'N/A')}/100)")
        return rules

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
            "avg_rating": round(sum(ratings)/len(ratings), 2) if ratings else None,
            "avg_reviews": round(sum(reviews)/len(reviews)) if reviews else None,
            "top_brokerages": list(set(brokerages))[:5],
            "common_specialties": list(set(specialties))[:10]
        }
