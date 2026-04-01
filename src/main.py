import asyncio
import json
from manager import AgentManager
from scraper_agent import ScraperAgent
from qualifier_agent import QualifierAgent
from business_analyzer import generate_business_input_page

async def main():
    print("🤖 Multi-Agent Zillow Lead Gen Starting...")
    
    # Initialize Manager (uses rotating Groq keys)
    manager = AgentManager()
    
    # STEP 1: Business Analysis
    business_url = input("Enter your business page URL: ") or "https://example-realestate.com"
    print("🔍 Agent 1: Analyzing business...")
    business_analysis = manager.analyze_business_page(business_url)
    print(f"Business: {business_analysis}")
    
    generate_business_input_page(business_url)
    
    # STEP 2: Manager decides targets
    print("🗺️ Agent 2: Planning scrape targets...")
    targets = manager.decide_scraping_targets()
    print(f"Targets: {targets[:3]}...")
    
    # STEP 3: Scraper Agent executes
    print("🕷️ Agent 3: Scraping agents...")
    all_agents = []
    
    async with ScraperAgent() as scraper:
        for target in targets:
            html = await scraper.scrape_url(target)
            agent_urls = scraper.extract_agent_urls(html)
            
            for url in agent_urls[:10]:  # Top 10 per directory
                agent_data = await scraper.scrape_agent_profile(url)
                if agent_data['properties_for_sale'] > 0:
                    all_agents.append(agent_data)
                await asyncio.sleep(1)
    
    print(f"Scraped {len(all_agents)} agents")
    
    # STEP 4: Manager creates qualification criteria
    criteria = manager.qualify_leads_instruction(all_agents)
    print(f"Qualification criteria: {criteria}")
    
    # STEP 5: Qualifier Agent
    print("⚖️ Agent 4: Qualifying leads...")
    qualifier = QualifierAgent(criteria)
    qualified_leads = qualifier.qualify_batch(all_agents)
    
    # Save results
    pd.DataFrame(qualified_leads).to_csv('output/qualified_leads.csv', index=False)
    manager.save_state()
    
    print(f"✅ {len(qualified_leads)} qualified leads saved to output/qualified_leads.csv")
    print("\nTop leads:")
    for lead in qualified_leads[:5]:
        print(f"  {lead['name_text'][:30]}... ({lead['properties_for_sale']} props)")

if __name__ == "__main__":
    asyncio.run(main())
