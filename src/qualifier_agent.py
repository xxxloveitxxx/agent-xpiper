import pandas as pd
from typing import List, Dict

class QualifierAgent:
    def __init__(self, criteria: Dict):
        self.criteria = criteria
    
    def qualify_batch(self, agents: List[Dict]) -> List[Dict]:
        qualified = []
        
        for agent in agents:
            score = 0
            reasons = []
            
            # Properties for sale (primary)
            props = agent.get('properties_for_sale', 0)
            if props >= self.criteria.get('min_properties_for_sale', 5):
                score += 50
            else:
                reasons.append(f"Low inventory: {props}")
            
            # Keyword match
            bio = agent.get('bio', '').lower()
            keywords = self.criteria.get('required_keywords', [])
            matches = sum(1 for kw in keywords if kw.lower() in bio)
            if matches > 0:
                score += 30
            
            # Geographic (if specified)
            geo_match = self.criteria.get('geographic_match', [])
            if not geo_match or any(city.lower() in agent.get('url', '').lower() for city in geo_match):
                score += 20
            
            agent['qualification_score'] = score
            agent['reasons'] = reasons
            agent['qualified'] = score >= self.criteria.get('score_threshold', 70)
            
            if agent['qualified']:
                qualified.append(agent)
        
        return qualified
