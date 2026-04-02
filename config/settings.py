import os
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "groq").lower()

GROQ_API_KEY_MANAGER   = os.getenv("GROQ_API_KEY_MANAGER", "")
GROQ_API_KEY_SCRAPER   = os.getenv("GROQ_API_KEY_SCRAPER", "")
GROQ_API_KEY_QUALIFIER = os.getenv("GROQ_API_KEY_QUALIFIER", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if PROVIDER == "gemini":
    MANAGER_MODEL   = os.getenv("MANAGER_MODEL",   "gemini-2.0-flash")
    SCRAPER_MODEL   = os.getenv("SCRAPER_MODEL",   "gemini-2.0-flash")
    QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", "gemini-2.0-flash")
else:
    MANAGER_MODEL   = os.getenv("MANAGER_MODEL",   "llama-3.3-70b-versatile")
    SCRAPER_MODEL   = os.getenv("SCRAPER_MODEL",   "llama-3.3-70b-versatile")
    QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", "llama-3.3-70b-versatile")

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
