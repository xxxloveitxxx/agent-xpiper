import asyncio
import csv
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

load_dotenv()

import config.settings as settings

from agents.manager import ManagerAgent
from agents.scraper import ScraperAgent

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logger = logging.getLogger("xpiper")
console = Console()


# ── CSV Export ─────────────────────────────────────────────────────────────

def export_all_scraped(agents, path="data/leads/all_scraped.csv") -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "name", "profile_url", "location", "brokerage",
        "rating", "review_count", "years_experience", "recent_sales",
        "phone", "email", "specialties", "languages", "about", "scraped_at",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for a in agents:
            writer.writerow({
                "name":             a.name,
                "profile_url":      a.profile_url,
                "location":         a.location,
                "brokerage":        a.brokerage,
                "rating":           a.rating,
                "review_count":     a.review_count,
                "years_experience": a.years_experience,
                "recent_sales":     a.recent_sales,
                "phone":            a.phone,
                "email":            a.email,
                "specialties":      " | ".join(a.specialties) if a.specialties else "",
                "languages":        " | ".join(a.languages) if a.languages else "",
                "about":            a.about,
                "scraped_at":       a.scraped_at,
            })

    return path


# ── Pipeline ───────────────────────────────────────────────────────────────

async def run():
    console.print(
        Panel.fit(
            "[bold cyan]Agent Xpiper[/bold cyan]  [dim]v1.0[/dim]\n"
            "[dim]AI-Powered Real Estate Lead Generation[/dim]",
            border_style="cyan",
        )
    )

    try:
        settings.validate()
    except EnvironmentError as e:
        console.print(f"[bold red]❌  {e}[/bold red]")
        sys.exit(1)

    manager = ManagerAgent()
    scraper = ScraperAgent()

    # ── Step 1: Load criteria & generate scraping plan ─────────────────
    console.print("\n[bold yellow]Step 1 — Manager: load criteria & build scraping plan[/bold yellow]")
    try:
        criteria = manager.load_criteria()
    except FileNotFoundError as e:
        console.print(f"[red]❌  {e}[/red]")
        sys.exit(1)

    biz_name = criteria.get("business_info", {}).get("name", "Unknown")
    console.print(f"[green]✓  Criteria loaded for:[/green] {biz_name}")

    scraping_plan = await manager.generate_scraping_instructions(criteria)
    n_urls = len(scraping_plan.get("zillow_search_urls", []))
    console.print(f"[green]✓  Scraping plan ready:[/green] {n_urls} Zillow search pages")

    # ── Step 2: Scrape Zillow ───────────────────────────────────────────
    console.print("\n[bold yellow]Step 2 — Scraper: fetch Zillow profiles[/bold yellow]")
    agent_profiles = await scraper.scrape_agents(scraping_plan)

    if not agent_profiles:
        console.print("[red]⚠  No profiles scraped. Check connectivity and criteria.[/red]")
        sys.exit(1)

    console.print(f"[green]✓  Profiles scraped:[/green] {len(agent_profiles)}")

    # ── Step 3: Export all scraped agents directly ─────────────────────
    console.print("\n[bold yellow]Step 3 — Exporting CSV[/bold yellow]")
    out = export_all_scraped(agent_profiles)
    console.print(f"[green]✓  Saved:[/green] {out}")

    # ── Summary ────────────────────────────────────────────────────────
    console.print(
        Panel.fit(
            f"[bold green]✅  Done![/bold green]\n"
            f"Scraped : {len(agent_profiles)} agents\n"
            f"Output  : {out}",
            border_style="green",
        )
    )
    return agent_profiles


if __name__ == "__main__":
    asyncio.run(run())
