from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class AgentProfile(BaseModel):
    profile_url: str
    name: Optional[str] = None
    location: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    years_experience: Optional[int] = None
    recent_sales: Optional[int] = None
    specialties: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    brokerage: Optional[str] = None
    about: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    scraped_at: Optional[str] = None


class QualifiedLead(BaseModel):
    agent: AgentProfile
    qualified: bool
    score: int = 0  # 0–100
    qualification_reasons: List[str] = Field(default_factory=list)
    disqualification_reason: Optional[str] = None
    qualified_at: Optional[str] = None
