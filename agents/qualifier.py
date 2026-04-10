# agents/qualifier.py
import asyncio
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

from config.settings import (
    GROQ_API_KEY_QUALIFIER, QUALIFIER_MODEL, PROVIDER, GROQ_MODELS
)
from core.llm_client import make_client, chat_with_fallback
from core.models import AgentProfile, QualifiedLead

logger = logging.getLogger(__name__)

BATCH_SIZE = 6  # Process agents in batches to manage context window


class QualifierAgent:

    def __init__(self):
        api_key = GROQ_API_KEY_QUALIFIER
        self._client, _ = make_client(api_key, QUALIFIER_MODEL)
        self._model_chain = GROQ_MODELS.get("qualifier", [QUALIFIER_MODEL])

    async def qualify_leads(self, agents: List[AgentProfile], rules: dict) -> List[QualifiedLead]:
        logger.info(f"Qualifier → processing {len(agents)} agents in batches of {BATCH_SIZE}")
        
        all_leads: List[QualifiedLead] = []
        batches = [agents[i: i + BATCH_SIZE] for i in range(0, len(agents), BATCH_SIZE)]
        
        for idx, batch in enumerate(batches, 1):
            logger.info(f"Qualifier → batch {idx}/{len(batches)}")
            results = await self._qualify_batch(batch, rules)
            all_leads.extend(results)
            # Small delay between batches to avoid rate limits
            if idx < len(batches):
                await asyncio.sleep(1)
        
        qualified = [l for l in all_leads if l.qualified]
        logger.info(f"Qualifier → {len(qualified)}/{len(agents)} agents qualified")
        return qualified

    async def _qualify_batch(self, agents: List[AgentProfile], rules: dict) -> List[QualifiedLead]:
        min_score = rules.get("min_score", 60)
        scoring_rules = rules.get("scoring_rules", [])
        disqualifiers = rules.get("disqualifiers", [])
        bonus_rules = rules.get("bonus_rules", [])
        
        # Prepare batch payload
        agents_payload = []
        for a in agents:
            agents_payload.append({
                "name": a.name,
                "brokerage": a.brokerage,
                "rating": a.rating,
                "review_count": a.review_count,
                "years_experience": a.years_experience,
                "recent_sales": a.recent_sales,
                "specialties": a.specialties,
                "languages": a.languages,
                "phone": a.phone,
                "email": a.email,
                "about": a.about[:200] if a.about else None,
                "profile_url": a.profile_url
            })

        prompt = f"""You are a real estate lead qualification expert.

=== SCORING RULES ===
Minimum score to qualify: {min_score}/100

Scoring rules (add points if condition met):
{json.dumps(scoring_rules, indent=2)}

Disqualifiers (auto-reject if ANY match):
{json.dumps(disqualifiers, indent=2)}

Bonus rules (extra points):
{json.dumps(bonus_rules, indent=2)}

=== AGENTS TO EVALUATE ===
{json.dumps(agents_payload, indent=2)}

=== OUTPUT FORMAT ===
Return a JSON array of qualification results. For EACH agent, output:
{{
  "profile_url": "https://...",
  "score": 85,
  "qualified": true,
  "reasons": ["Rating 5.0 earns max points", "Recent sales bonus: 10"],
  "disqualified_reason": null  // or string if disqualified
}}

Rules:
- Return ONLY a valid JSON array, no explanations, no markdown
- Score must be integer 0-100
- qualified = true ONLY if score >= {min_score} AND no disqualifier matched
- reasons: list 2-4 specific, human-readable justifications for the score
- If disqualified, set qualified=false and populate disqualified_reason
- Process ALL agents in the input array

Output JSON array only:"""

        try:
            resp_text = await chat_with_fallback(
                client=self._client,
                messages=[{"role": "user", "content": prompt}],
                model_chain=self._model_chain,
                json_mode=True,
                max_tokens=2000,
                temperature=0.1,
            )
            
            results = json.loads(resp_text)
            if not isinstance(results, list):
                logger.warning("Qualifier → LLM returned non-array, wrapping in list")
                results = [results]
            
            leads = []
            for i, agent in enumerate(agents):
                try:
                    r = results[i] if i < len(results) else {}
                    lead = QualifiedLead(
                        name=agent.name,
                        profile_url=agent.profile_url,
                        location=agent.location,
                        brokerage=agent.brokerage,
                        rating=agent.rating,
                        reviews=agent.review_count,
                        years_experience=agent.years_experience,
                        recent_sales=agent.recent_sales,
                        specialties=agent.specialties,
                        languages=agent.languages,
                        phone=agent.phone,
                        email=agent.email,
                        about=agent.about,
                        qualification_score=r.get("score", 0),
                        qualification_reasons=r.get("reasons", []),
                        disqualified_reason=r.get("disqualified_reason"),
                        scraped_at=agent.scraped_at,
                        qualified_at=datetime.utcnow().isoformat(),
                        qualified=r.get("qualified", False)
                    )
                    leads.append(lead)
                except Exception as e:
                    logger.error(f"Qualifier → failed to parse result for agent {i}: {e}")
                    # Fallback: create minimal lead
                    leads.append(QualifiedLead(
                        name=agent.name,
                        profile_url=agent.profile_url,
                        qualification_score=0,
                        qualification_reasons=["Parsing error"],
                        qualified=False,
                        scraped_at=agent.scraped_at,
                        qualified_at=datetime.utcnow().isoformat()
                    ))
            
            return leads
            
        except Exception as exc:
            logger.error(f"Qualifier → batch failed: {exc}")
            # Fallback: return all as unqualified
            return [
                QualifiedLead(
                    name=a.name,
                    profile_url=a.profile_url,
                    qualification_score=0,
                    qualification_reasons=[f"Error: {str(exc)[:100]}"],
                    qualified=False,
                    scraped_at=a.scraped_at,
                    qualified_at=datetime.utcnow().isoformat()
                )
                for a in agents
            ]
