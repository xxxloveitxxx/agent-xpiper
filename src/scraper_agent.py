import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

class ScraperAgent:
    def __init__(self):
        self.jina_key = os.getenv('JINA_READER_API_KEY')
        self.session = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def scrape_url(self, url: str) -> str:
        if not self.jina_key:
            return f"ERROR: Jina key missing for {url}"
        
        jina_url = f"https://r.jina.ai/{url}"
        params = {'api_key': self.jina_key}
        
        try:
            async with self.session.get(jina_url, params=params) as resp:
                return await resp.text() if resp.status == 200 else f"HTTP {resp.status}"
        except Exception as e:
            return f"ERROR: {e}"
    
    def extract_agent_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        agents = set()
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/profile/' in href and 'zillow.com' in href:
                agents.add(href)
        
        return list(agents)[:20]  # Top 20 per directory
    
    async def scrape_agent_profile(self, profile_url: str) -> Dict:
        html = await self.scrape_url(profile_url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract key data
        data = {
            'url': profile_url,
            'name': soup.find('h1') or soup.find('.agent-name'),
            'name_text': (soup.find('h1') or soup.find('.agent-name') or {}).get_text(strip=True) if soup.find('h1') or soup.find('.agent-name') else '',
            'properties_for_sale': 0,
            'phone': '',
            'bio': ''
        }
        
        # Find listings count
        listings_text = soup.get_text()
        prop_matches = re.findall(r'(\d+)\s*(?:homes?|properties|listings)\s*for\s*sale', listings_text, re.I)
        data['properties_for_sale'] = int(prop_matches[0]) if prop_matches else 0
        
        # Phone extraction
        phone_match = re.search(r'[\+]?[\d\s\-\(\)]{10,}', listings_text)
        data['phone'] = phone_match.group() if phone_match else ''
        
        data['bio'] = soup.find('.agent-bio', text=True) or ''
        
        return data
