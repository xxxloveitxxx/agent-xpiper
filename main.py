import asyncio
import csv
import json
import logging
import sys
from datetime import datetime
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

def export_all_scraped(agents, cities: list, path: str = None) -> str:
    # Include city slug and timestamp in filename so each run doesn't overwrite
    if path is None:
        city_slug = "_".join(c.lower().replace(", ", "-").replace(" ", "-") for c in cities)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
        path = f"data/leads/scraped_{city_slug}_{timestamp}.csv"

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "name", "profile_url", "location", "brokerage",
        "rating", "review_count", "years_experience", "recent_sales",
        "for_sale_count", "for_sale_address", "recent_sale_address",
        "phone", "email", "specialties", "languages", "about", "scraped_at",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for a in agents:
            writer.writerow({
                "name":                a.name,
                "profile_url":         a.profile_url,
                "location":            a.location,
                "brokerage":           a.brokerage,
                "rating":              a.rating,
                "review_count":        a.review_count,
                "years_experience":    a.years_experience,
                "recent_sales":        a.recent_sales,
                "for_sale_count":      a.for_sale_count,
                "for_sale_address":    a.for_sale_address,
                "recent_sale_address": a.recent_sale_address,
                "phone":               a.phone,
                "email":               a.email,
                "specialties":         " | ".join(a.specialties) if a.specialties else "",
                "languages":           " | ".join(a.languages) if a.languages else "",
                "about":               a.about,
                "scraped_at":          a.scraped_at,
            })

    return path


def mark_cities_scraped(cities: list) -> None:
    """Append scraped cities to the progress tracker."""
    scraped_path = Path("data/leads/scraped_cities.json")
    scraped_path.parent.mkdir(parents=True, exist_ok=True)

    scraped: list = []
    if scraped_path.exists():
        with open(scraped_path, "r") as f:
            scraped = json.load(f)

    for city in cities:
        if city not in scraped:
            scraped.append(city)

    with open(scraped_path, "w") as f:
        json.dump(scraped, f, indent=2)

    logger.info(f"Progress saved — {len(scraped)} cities scraped total")


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

    # ── Step 1: Load criteria & build scraping plan ────────────────────
    console.print("\n[bold yellow]Step 1 — Manager: load criteria & build scraping plan[/bold yellow]")
    try:
        criteria = manager.load_criteria()
    except FileNotFoundError as e:
        console.print(f"[red]❌  {e}[/red]")
        sys.exit(1)

    biz_name      = criteria.get("business_info", {}).get("name", "Unknown")
    current_cities = criteria.get("target_market", {}).get("locations", [])
    console.print(f"[green]✓  Criteria loaded for:[/green] {biz_name}")
    console.print(f"[green]✓  Cities this run:[/green] {', '.join(current_cities)}")

    scraping_plan = await manager.generate_scraping_instructions(criteria)
    n_urls = len(scraping_plan.get("zillow_search_urls", []))
    console.print(f"[green]✓  Scraping plan ready:[/green] {n_urls} Zillow search pages")

    # ── Step 2: Scrape Zillow ──────────────────────────────────────────
    console.print("\n[bold yellow]Step 2 — Scraper: fetch Zillow profiles[/bold yellow]")
    agent_profiles = await scraper.scrape_agents(scraping_plan)

    if not agent_profiles:
        console.print("[red]⚠  No profiles scraped. Check connectivity and criteria.[/red]")
        # Still mark city as attempted so we advance on next run
        mark_cities_scraped(current_cities)
        sys.exit(1)

    console.print(f"[green]✓  Profiles scraped:[/green] {len(agent_profiles)}")

    # ── Step 3: Export CSV ─────────────────────────────────────────────
    console.print("\n[bold yellow]Step 3 — Exporting CSV[/bold yellow]")
    out = export_all_scraped(agent_profiles, current_cities)
    console.print(f"[green]✓  Saved:[/green] {out}")

    # ── Step 4: Mark cities as scraped ────────────────────────────────
    mark_cities_scraped(current_cities)

    # ── Summary ───────────────────────────────────────────────────────
    # Check how many cities remain in the cycle
    cities_path  = Path("config/cities.json")
    scraped_path = Path("data/leads/scraped_cities.json")
    remaining_info = ""
    if cities_path.exists() and scraped_path.exists():
        with open(cities_path) as f:
            all_cities = json.load(f)
        with open(scraped_path) as f:
            scraped = json.load(f)
        remaining = [c for c in all_cities if c not in scraped]
        remaining_info = f"\nRemaining : {len(remaining)}/{len(all_cities)} cities"

    console.print(
        Panel.fit(
            f"[bold green]✅  Done![/bold green]\n"
            f"Cities  : {', '.join(current_cities)}\n"
            f"Scraped : {len(agent_profiles)} agents\n"
            f"Output  : {out}"
            f"{remaining_info}",
            border_style="green",
        )
    )
    return agent_profiles


if __name__ == "__main__":
    asyncio.run(run())
