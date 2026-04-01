import json
import logging
from datetime import datetime
from typing import List

from groq import Groq

from config.settings import GROQ_API_KEY_QUALIFIER, QUALIFIER_MODEL
from core.models import AgentProfile, QualifiedLead

logger = logging.getLogger(__name__)

BATCH_SIZE = 6  # agents per LLM call — balance accuracy vs speed


class QualifierAgent:
    """
    The Qualifier Agent scores each scraped agent against the
    Manager-generated rules and returns only qualified leads.
    """

    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY_QUALIFIER)
        self.model = QUALIFIER_MODEL

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def qualify_leads(
        self, agents: List[AgentProfile], rules: dict
    ) -> List[QualifiedLead]:

        logger.info(f"Qualifier → processing {len(agents)} agents in batches of {BATCH_SIZE}")

        all_leads: List[QualifiedLead] = []
        batches = [agents[i: i + BATCH_SIZE] for i in range(0, len(agents), BATCH_SIZE)]

        for idx, batch in enumerate(batches, 1):
            logger.info(f"Qualifier → batch {idx}/{len(batches)}")
            results = self._qualify_batch(batch, rules)
            all_leads.extend(results)

        qualified = [l for l in all_leads if l.qualified]
        logger.info(
            f"Qualifier → {len(qualified)}/{len(agents)} agents qualified"
        )
        return qualified

    # ------------------------------------------------------------------ #
    #  Batch processing                                                    #
    # ------------------------------------------------------------------ #

    def _qualify_batch(
        self, agents: List[AgentProfile], rules: dict
    ) -> List[QualifiedLead]:

        agents_payload = []
        for a in agents:
            agents_payload.append({
                "profile_url": a.profile_url,
                "name": a.name,
                "location": a.location,
                "rating": a.rating,
                "review_count": a.review_count,
                "years_experience": a.years_experience,
                "recent_sales": a.recent_sales,
                "brokerage": a.brokerage,
                "specialties": a.specialties,
                "about": (a.about[:300] + "...") if a.about and len(a.about) > 300 else a.about,
            })

        prompt = f"""You are a lead qualification expert for a B2B sales team.

Qualification rules (set by the manager):
{json.dumps(rules, indent=2)}

Agents to evaluate:
{json.dumps(agents_payload, indent=2)}

For each agent, apply the scoring rubric and hard disqualifiers strictly.

Return ONLY valid JSON:
{{
  "results": [
    {{
      "profile_url": "must match exactly",
      "qualified": true,
      "score": 75,
      "qualification_reasons": ["Strong review count of 45", "Rating 4.8 earns max points"],
      "disqualification_reason": null
    }},
    {{
      "profile_url": "must match exactly",
      "qualified": false,
      "score": 20,
      "qualification_reasons": [],
      "disqualification_reason": "Only 2 reviews — below hard minimum"
    }}
  ]
}}

Rules:
- results array must have exactly {len(agents_payload)} items in the same order
- score must be 0-100 integer
- qualified must be true only if score >= minimum_score_to_qualify AND no hard disqualifiers triggered"""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2000,
            )

            data = json.loads(resp.choices[0].message.content)
            results = data.get("results", [])

            leads: List[QualifiedLead] = []
            for agent, result in zip(agents, results):
                leads.append(QualifiedLead(
                    agent=agent,
                    qualified=bool(result.get("qualified", False)),
                    score=int(result.get("score", 0)),
                    qualification_reasons=result.get("qualification_reasons", []),
                    disqualification_reason=result.get("disqualification_reason"),
                    qualified_at=datetime.utcnow().isoformat(),
                ))
            return leads

        except Exception as exc:
            logger.error(f"Qualifier → batch failed: {exc}")
            return [
                QualifiedLead(
                    agent=a,
                    qualified=False,
                    score=0,
                    disqualification_reason=f"Processing error: {exc}",
                )
                for a in agents
            ]
