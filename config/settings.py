# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "groq").lower()

GROQ_API_KEY_MANAGER   = os.getenv("ROQ_API_KEY_MANAGER", "")
GROQ_API_KEY_SCRAPER   = os.getenv("GROQ_API_KEY_SCRAPER", "")
GROQ_API_KEY_QUALIFIER = os.getenv("GROQ_API_KEY_QUALIFIER", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# === GROQ MODEL FALLBACK CHAINS (Free Tier Only) ===
# Order: Primary → Fallback 1 → Fallback 2
# All models below are free on Groq: https://console.groq.com/docs/models
GROQ_MODELS = {
    "manager": [
        "llama-3.3-70b-versatile",  # Primary: best reasoning
        "mixtral-8x7b-32768",       # Fallback 1: good balance, larger context
        "llama-3.1-8b-instant"      # Fallback 2: fast, low rate limits
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

if PROVIDER == "gemini":
    MANAGER_MODEL   = os.getenv("MANAGER_MODEL",   "gemini-2.0-flash")
    SCRAPER_MODEL   = os.getenv("SCRAPER_MODEL",   "gemini-2.0-flash")
    QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", "gemini-2.0-flash")
else:
    # Use first model in chain as default
    MANAGER_MODEL   = os.getenv("MANAGER_MODEL",   GROQ_MODELS["manager"][0])
    SCRAPER_MODEL   = os.getenv("SCRAPER_MODEL",   GROQ_MODELS["scraper"][0])
    QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", GROQ_MODELS["qualifier"][0])

REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2.5"))


def validate():
    if PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY is missing.\n"
                "Get a free key at https://aistudio.google.com/app/apikey"
            )
    else:
        missing = [
            name for name, val in [
                ("GROQ_API_KEY_MANAGER",   GROQ_API_KEY_MANAGER),
                ("GROQ_API_KEY_SCRAPER",   GROQ_API_KEY_SCRAPER),
                ("GROQ_API_KEY_QUALIFIER", GROQ_API_KEY_QUALIFIER),
            ] if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Missing required variables: {', '.join(missing)}\n"
                "Add them to .env or GitHub Secrets."
            )
