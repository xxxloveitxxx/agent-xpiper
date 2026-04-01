import json
import os
from typing import Dict, List
from groq import Groq
import random

class AgentManager:
    def __init__(self):
        self.groq_keys = os.getenv('GROQ_API_KEYS').split(',')
        self.context = {
            'business': {},
            'scraping_targets': [],
            'qualified_leads': [],
            'stage': 'analyze_business'
        }
    
    def get_client(self) -> Groq:
        key = random.choice(self.groq_keys)
        return Groq(api_key=key)
    
    def analyze_business_page(self, business_url: str) -> Dict:
        """Agent 1: Analyze your business page to understand lead criteria"""
        client = self.get_client()
        
        prompt = f"""
        Analyze this business page: {business_url}
        
        Extract:
        1. Business type (luxury real estate, investors, first-time buyers?)
        2. Target agent profile (high-volume sellers, luxury specialists?)
        3. Geographic focus (cities/states)
        4. Min properties for sale threshold
        
        Respond JSON only:
        ```json
        {{
            "business_type": "...",
            "target_agent_profile": "...", 
            "geographic_focus": ["city1", "city2"],
            "min_properties_threshold": 5,
            "zillow_search_terms": ["luxury", "investor"]
        }}
        ```
        """
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-70b-versatile",
            temperature=0.1
        )
        
        try:
            analysis = json.loads(chat_completion.choices[0].message.content)
            self.context['business'] = analysis
            return analysis
        except:
            return {"error": "Analysis failed"}
    
    def decide_scraping_targets(self) -> List[str]:
        """Agent 2: Manager decides where Scraper should go"""
        client = self.get_client()
        
        prompt = f"""
        Based on business: {json.dumps(self.context['business'])}
        
        Generate TOP 10 Zillow agent directory URLs to scrape.
        Focus on {self.context['business'].get('geographic_focus', 'US markets')}
        Target agents matching: {self.context['business'].get('target_agent_profile', 'active sellers')}
        
        Return JSON array only:
        ["https://www.zillow.com/agents/fl/miami/", ...]
        """
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-70b-versatile",
            temperature=0.3
        )
        
        try:
            targets = json.loads(chat_completion.choices[0].message.content)
            self.context['scraping_targets'] = targets[:10]
            return targets
        except:
            # Fallback US targets
            return ["https://www.zillow.com/agents/fl/miami/", "https://www.zillow.com/agents/ca/los-angeles/"]
    
    def qualify_leads_instruction(self, leads: List[Dict]) -> Dict:
        """Agent 3: Manager tells Qualifier what criteria to use"""
        client = self.get_client()
        
        sample_lead = leads[0] if leads else {}
        prompt = f"""
        Business needs: {json.dumps(self.context['business'])}
        Sample agent data: {json.dumps(sample_lead)}
        
        Create qualification criteria JSON:
        {{
            "min_properties_for_sale": 5,
            "required_keywords": ["luxury", "investment"],
            "geographic_match": ["Miami", "Fort Lauderdale"],
            "score_threshold": 70
        }}
        """
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-70b-versatile",
            temperature=0.1
        )
        
        try:
            criteria = json.loads(chat_completion.choices[0].message.content)
            return criteria
        except:
            return {"min_properties_for_sale": 5}
    
    def save_state(self):
        with open('output/agent_log.json', 'w') as f:
            json.dump(self.context, f, indent=2)
