import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY_MANAGER = os.getenv("GROQ_API_KEY_MANAGER", "")
GROQ_API_KEY_SCRAPER = os.getenv("GROQ_API_KEY_SCRAPER", "")
GROQ_API_KEY_QUALIFIER = os.getenv("GROQ_API_KEY_QUALIFIER", "")
JINA_API_KEY = os.getenv("JINA_API_KEY", "")

MANAGER_MODEL = os.getenv("MANAGER_MODEL", "llama-3.3-70b-versatile")
SCRAPER_MODEL = os.getenv("SCRAPER_MODEL", "llama-3.3-70b-versatile")
QUALIFIER_MODEL = os.getenv("QUALIFIER_MODEL", "llama-3.3-70b-versatile")

REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "2.5"))


def validate():
    missing = []
    for name, val in [
        ("GROQ_API_KEY_MANAGER", GROQ_API_KEY_MANAGER),
        ("GROQ_API_KEY_SCRAPER", GROQ_API_KEY_SCRAPER),
        ("GROQ_API_KEY_QUALIFIER", GROQ_API_KEY_QUALIFIER),
    ]:
        if not val:
            missing.append(name)
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Add them to your .env file or GitHub repository secrets."
        )
