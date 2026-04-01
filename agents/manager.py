import json
import logging
from groq import Groq
from pathlib import Path
from config.settings import GROQ_API_KEY_MANAGER, MANAGER_MODEL

logger = logging.getLogger(__name__)


class ManagerAgent:
    """
    The Manager Agent orchestrates the entire pipeline.
    It reads the business criteria, generates a scraping plan,
    and then generates qualification rules for the Qualifier.
    """

    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY_MANAGER)
        self.model = MANAGER_MODEL

    # ------------------------------------------------------------------ #
    #  Criteria                                                            #
    # ------------------------------------------------------------------ #

    def load_criteria(self) -> dict:
        path = Path("config/criteria.json")
        if not path.exists():
            raise FileNotFoundError(
                "config/criteria.json not found.\n"
                "Open the GitHub Pages site and fill out the form to generate it."
            )
        with open(path) as f:
            return json.load(f)

    # ------------------------------------------------------------------ #
    #  Step 1 — Scraping Plan                                             #
    # ------------------------------------------------------------------ #

    def generate_scraping_instructions(self, criteria: dict) -> dict:
        logger.info("Manager → generating scraping plan...")

        locations = criteria.get("target_market", {}).get("locations", ["United States"])
        max_pages = criteria.get("scraping_config", {}).get("max_pages", 3)
        max_agents = criteria.get("scraping_config", {}).get("max_agents", 50)

        prompt = f"""You are the manager of an AI lead generation system targeting real estate agents on Zillow.

Business context:
{json.dumps(criteria, indent=2)}

Your job: generate a precise JSON scraping plan.

Rules:
- Zillow agent search URL pattern: https://www.zillow.com/agent-finder/real-estate-agent-reviews/?location=CITY%2C+STATE&page=N
- Generate one URL per page per location (up to {max_pages} pages each)
- URL-encode the location (spaces → +, commas → %2C)
- Locations to cover: {locations}

Return ONLY valid JSON matching this schema exactly:
{{
  "zillow_search_urls": [
    "https://www.zillow.com/agent-finder/real-estate-agent-reviews/?location=Miami%2C+FL&page=1"
  ],
  "fields_to_extract": [
    "name", "rating", "review_count", "years_experience",
    "recent_sales", "brokerage", "specialties", "languages",
    "phone", "about", "location"
  ],
  "max_agents": {max_agents},
  "scraping_notes": "Brief note on what to prioritize"
}}"""

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        plan = json.loads(resp.choices[0].message.content)
        logger.info(f"Manager → plan ready: {len(plan.get('zillow_search_urls', []))} URLs")
        return plan

    # ------------------------------------------------------------------ #
    #  Step 2 — Qualification Rules                                       #
    # ------------------------------------------------------------------ #

    def generate_qualification_rules(self, criteria: dict, agents_summary: dict) -> dict:
        logger.info("Manager → generating qualification rules...")

        prompt = f"""You are the manager of an AI lead qualification system.

Business info:
{json.dumps(criteria.get('business_info', {}), indent=2)}

Qualification criteria from the business owner:
{json.dumps(criteria.get('qualification_criteria', {}), indent=2)}

We have scraped {agents_summary.get('total_agents', 0)} agent profiles with these fields:
{agents_summary.get('available_fields', [])}

Generate a precise qualification ruleset. Return ONLY valid JSON:
{{
  "hard_disqualifiers": [
    "review_count < {criteria.get('qualification_criteria', {}).get('min_reviews', 5)}",
    "rating < {criteria.get('qualification_criteria', {}).get('min_rating', 4.0)}"
  ],
  "minimum_score_to_qualify": 60,
  "scoring_rubric": {{
    "review_count": {{
      "0-4": 0,
      "5-14": 15,
      "15-29": 25,
      "30-59": 35,
      "60+": 45
    }},
    "rating": {{
      "below_3.5": 0,
      "3.5-3.9": 10,
      "4.0-4.4": 20,
      "4.5-4.7": 28,
      "4.8-5.0": 35
    }},
    "years_experience": {{
      "0": 0,
      "1-2": 8,
      "3-5": 15,
      "6-10": 20,
      "10+": 25
    }},
    "recent_sales_bonus": "Describe bonus points for high recent sales",
    "custom_bonus": "Describe any business-specific bonuses"
  }},
  "qualification_context": "Plain-English summary of what makes a great lead for this specific business",
  "priority_fields": ["review_count", "rating", "years_experience"]
}}"""

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        rules = json.loads(resp.choices[0].message.content)
        logger.info(
            f"Manager → rules ready (min score: {rules.get('minimum_score_to_qualify', 60)})"
        )
        return rules
