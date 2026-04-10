# agents/qualifier.py
import asyncio
import json
import logging
from typing import List
from datetime import datetime

from config.settings import (
    GROQ_API_KEY_QUALIFIER, QUALIFIER_MODEL, GROQ_MODELS
)
from core.llm_client import make_client, chat_with_fallback
from core.models import AgentProfile, QualifiedLead

logger = logging.getLogger(__name__)

BATCH_SIZE = 6


class QualifierAgent:

    def __init__(self):
        api_key = GROQ_API_KEY_QUALIFIER
        self._client = make_client(api_key, QUALIFIER_MODEL)
        self._model_chain = GROQ_MODELS.get("qualifier", [QUALIFIER_MODEL])

    async def qualify_leads(self, agents: List[AgentProfile], rules: dict) -> List[QualifiedLead]:
        logger.info(f"Qualifier → processing {len(agents)} agents in batches of {BATCH_SIZE}")

        all_leads: List[QualifiedLead] = []
        batches = [agents[i: i + BATCH_SIZE] for i in range(0, len(agents), BATCH_SIZE)]

        for idx, batch in enumerate(batches, 1):
            logger.info(f"Qualifier → batch {idx}/{len(batches)}")
            results = await self._qualify_batch(batch, rules)
            all_leads.extend(results)
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

        agents_payload = []
        for a in agents:
            agents_payload.append({
                "profile_url": a.profile_url,
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
Return a JSON array with one object per agent, in the same order as input:
[
  {{
    "profile_url": "https://...",
    "score": 85,
    "qualified": true,
    "qualification_reasons": ["Rating 5.0 earns max points", "10+ recent sales bonus"],
    "disqualification_reason": null
  }},
  ...
]

Rules:
- Return ONLY a valid JSON array, no markdown, no explanations
- score must be integer 0-100
- qualified = true ONLY if score >= {min_score} AND no disqualifier matched
- qualification_reasons: 2-4 specific human-readable justifications
- disqualification_reason: null if qualified, otherwise a string explaining why
- Output exactly {len(agents_payload)} objects, one per agent

JSON array only:"""

        try:
            resp_text = await chat_with_fallback(
                client=self._client,
                messages=[{"role": "user", "content": prompt}],
                model_chain=self._model_chain,
                json_mode=True,
                max_tokens=2000,
                temperature=0.1,
            )

            # Strip markdown fences if present
            cleaned = resp_text.strip().strip("```json").strip("```").strip()
            parsed = json.loads(cleaned)

            # LLM sometimes returns {"results": [...]} instead of bare array
            if isinstance(parsed, dict):
                for key in ("results", "agents", "leads", "data"):
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break
                else:
                    # Single object returned — wrap it
                    parsed = [parsed]

            results = parsed if isinstance(parsed, list) else [parsed]

            # Build a lookup by profile_url in case LLM reorders
            result_map = {r.get("profile_url", ""): r for r in results if isinstance(r, dict)}

            leads = []
            for i, agent in enumerate(agents):
                try:
                    # Match by profile_url first, fall back to positional
                    r = result_map.get(agent.profile_url) or (results[i] if i < len(results) else {})

                    lead = QualifiedLead(
                        agent=agent,
                        score=int(r.get("score", 0)),
                        qualified=bool(r.get("qualified", False)),
                        qualification_reasons=r.get("qualification_reasons", []),
                        disqualification_reason=r.get("disqualification_reason"),
                        qualified_at=datetime.utcnow().isoformat(),
                    )
                    leads.append(lead)

                except Exception as e:
                    logger.error(f"Qualifier → failed to parse result for agent {i} ({agent.profile_url}): {e}")
                    leads.append(QualifiedLead(
                        agent=agent,
                        score=0,
                        qualified=False,
                        qualification_reasons=["Parsing error — scored 0 by default"],
                        qualified_at=datetime.utcnow().isoformat(),
                    ))

            return leads

        except Exception as exc:
            logger.error(f"Qualifier → batch failed: {exc}")
            return [
                QualifiedLead(
                    agent=a,
                    score=0,
                    qualified=False,
                    qualification_reasons=[f"Batch error: {str(exc)[:100]}"],
                    qualified_at=datetime.utcnow().isoformat(),
                )
                for a in agents
            ]
