import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from core.models import QualifiedLead
import logging

logger = logging.getLogger(__name__)


def export_qualified_leads(
    leads: List[QualifiedLead],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Export qualified leads to a CSV file sorted by score."""

    if not leads:
        logger.warning("No qualified leads to export.")
        return None

    rows = []
    for lead in leads:
        a = lead.agent
        rows.append({
            "Name": a.name,
            "Profile URL": a.profile_url,
            "Location": a.location,
            "Brokerage": a.brokerage,
            "Rating": a.rating,
            "Reviews": a.review_count,
            "Years Experience": a.years_experience,
            "Recent Sales": a.recent_sales,
            "Specialties": ", ".join(a.specialties) if a.specialties else "",
            "Languages": ", ".join(a.languages) if a.languages else "",
            "Phone": a.phone,
            "Email": a.email,
            "About (truncated)": (a.about[:300] + "...") if a.about and len(a.about) > 300 else a.about,
            "Qualification Score": lead.score,
            "Qualification Reasons": "; ".join(lead.qualification_reasons),
            "Scraped At": a.scraped_at,
            "Qualified At": lead.qualified_at,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("Qualification Score", ascending=False)

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/leads/qualified_leads_{ts}.csv"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Exported {len(rows)} leads → {output_path}")
    return output_path
