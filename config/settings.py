# config/settings.py — Groq-only version
import os
from dotenv import load_dotenv

load_dotenv()

PROVIDER = "groq"
# Groq API keys (one per agent role for better rate limit distribution)
GROQ_API_KEY_MANAGER   = os.getenv("GROQ_API_KEY_MANAGER", "")
GROQ_API_KEY_SCRAPER   = os.getenv("GROQ_API_KEY_SCRAPER", "")
GROQ_API_KEY_QUALIFIER = os.getenv("GROQ_API_KEY_QUALIFIER", "")

# === GROQ MODEL FALLBACK CHAINS (Free Tier Only) ===
GROQ_MODELS = {
    "manager": [
        "llama-3.3-70b-versatile",  # Primary: best reasoning
        "mixtral-8x7b-32768",       # Fallback 1: good balance
        "llama-3.1-8b-instant"      # Fallback 2: fast, low limits
    ],
    "scraper": [
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768", 
        "llama-3.1-8b-instant"
    ],
    "qualifier": [
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant"
    ]
}

# Default models (first in chain)
MANAGER_MODEL   = os.getenv("MANAGER_MODEL",   GROQ_MODELS["manager"][0])
SCRAPER_MODEL   = os.getenv("SCRAPER_MODEL",   GROQ_MODELS["scraper"][0])
QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", GROQ_MODELS["qualifier"][0])

REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2.5"))


def validate():
    """Validate required Groq API keys are present."""
    missing = [
        name for name, val in [
            ("GROQ_API_KEY_MANAGER",   GROQ_API_KEY_MANAGER),
            ("GROQ_API_KEY_SCRAPER",   GROQ_API_KEY_SCRAPER),
            ("GROQ_API_KEY_QUALIFIER", GROQ_API_KEY_QUALIFIER),
        ] if not val
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required GROQ API keys: {', '.join(missing)}\n"
            "Get free keys at https://console.groq.com/keys\n"
            "Add them to .env or GitHub Secrets."
        )
