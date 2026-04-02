import asyncio
import logging
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

load_dotenv()

# Temporary debug — remove after confirming
import os
print("SCRAPINGANT:", bool(os.getenv("SCRAPINGANT_API_KEY")))
print("WEBSCRAPINGAPI:", bool(os.getenv("WEBSCRAPINGAPI_KEY")))
print("SCRAPEDO:", bool(os.getenv("SCRAPEDO_API_KEY")))

import config.settings as settings  # noqa: E402 — must load .env first

from agents.manager import ManagerAgent
from agents.qualifier import QualifierAgent
from agents.scraper import ScraperAgent
from core.csv_exporter import export_qualified_leads

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logger = logging.getLogger("xpiper")
console = Console()


# ── Pipeline ───────────────────────────────────────────────────────────────

async def run():
    console.print(
        Panel.fit(
            "[bold cyan]Agent Xpiper[/bold cyan]  [dim]v1.0[/dim]\n"
            "[dim]AI-Powered Real Estate Lead Generation[/dim]",
            border_style="cyan",
        )
    )

    # Validate environment
    try:
        settings.validate()
    except EnvironmentError as e:
        console.print(f"[bold red]❌  {e}[/bold red]")
        sys.exit(1)

    manager = ManagerAgent()
    scraper = ScraperAgent()
    qualifier = QualifierAgent()

    # ── Step 1: Load criteria & generate scraping plan ─────────────────
    console.print("\n[bold yellow]Step 1 — Manager: load criteria & build scraping plan[/bold yellow]")
    try:
        criteria = manager.load_criteria()
    except FileNotFoundError as e:
        console.print(f"[red]❌  {e}[/red]")
        sys.exit(1)

    biz_name = criteria.get("business_info", {}).get("name", "Unknown")
    console.print(f"[green]✓  Criteria loaded for:[/green] {biz_name}")

    scraping_plan = manager.generate_scraping_instructions(criteria)
    n_urls = len(scraping_plan.get("zillow_search_urls", []))
    console.print(f"[green]✓  Scraping plan ready:[/green] {n_urls} Zillow search pages")

    # ── Step 2: Scrape Zillow ───────────────────────────────────────────
    console.print("\n[bold yellow]Step 2 — Scraper: fetch Zillow profiles via Jina AI[/bold yellow]")
    agent_profiles = await scraper.scrape_agents(scraping_plan)

    if not agent_profiles:
        console.print("[red]⚠  No profiles scraped. Check Jina connectivity and your criteria.[/red]")
        sys.exit(1)

    console.print(f"[green]✓  Profiles scraped:[/green] {len(agent_profiles)}")

    # ── Step 3: Generate qualification rules ───────────────────────────
    console.print("\n[bold yellow]Step 3 — Manager: generate qualification rules[/bold yellow]")
    summary = {
        "total_agents": len(agent_profiles),
        "available_fields": ["name", "rating", "review_count", "years_experience",
                             "recent_sales", "brokerage", "specialties", "about"],
    }
    qual_rules = manager.generate_qualification_rules(criteria, summary)
    min_score = qual_rules.get("minimum_score_to_qualify", 60)
    console.print(f"[green]✓  Rules ready:[/green] minimum score {min_score}/100")

    # ── Step 4: Qualify leads ──────────────────────────────────────────
    console.print("\n[bold yellow]Step 4 — Qualifier: score & filter agents[/bold yellow]")
    qualified = qualifier.qualify_leads(agent_profiles, qual_rules)
    console.print(f"[green]✓  Qualified leads:[/green] {len(qualified)}/{len(agent_profiles)}")

    # ── Step 5: Export CSV ─────────────────────────────────────────────
    console.print("\n[bold yellow]Step 5 — Exporting CSV[/bold yellow]")
    if qualified:
        out = export_qualified_leads(qualified)
        console.print(f"[green]✓  Saved:[/green] {out}")
    else:
        console.print("[yellow]⚠  No qualified leads to export.[/yellow]")
        out = None

    # ── Summary ────────────────────────────────────────────────────────
    console.print(
        Panel.fit(
            f"[bold green]✅  Done![/bold green]\n"
            f"Scraped   : {len(agent_profiles)} agents\n"
            f"Qualified : {len(qualified)} leads\n"
            f"Output    : {out or 'N/A'}",
            border_style="green",
        )
    )
    return qualified


if __name__ == "__main__":
    asyncio.run(run())
