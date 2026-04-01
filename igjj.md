# ⚡ Agent Xpiper

AI-powered real estate lead generation using a 3-agent pipeline:
**Manager → Scraper → Qualifier**

## Quick Start

### 1. Add GitHub Secrets
Go to `Settings → Secrets → Actions` and add:

| Secret | Description |
|---|---|
| `GROQ_API_KEY_MANAGER` | Groq key for the Manager agent |
| `GROQ_API_KEY_SCRAPER` | Groq key for the Scraper agent |
| `GROQ_API_KEY_QUALIFIER` | Groq key for the Qualifier agent |
| `JINA_API_KEY` | *(Optional)* Jina AI key for higher rate limits |

Get free Groq keys at [console.groq.com](https://console.groq.com).  
Get a Jina key at [jina.ai](https://jina.ai).

### 2. Enable GitHub Pages
`Settings → Pages → Source: Deploy from branch → Branch: main → Folder: /docs`

### 3. Configure your criteria
Open your GitHub Pages URL, fill out the form, download `criteria.json`,
and commit it to `config/criteria.json`.

### 4. Run
Pushing `config/criteria.json` triggers the pipeline automatically.
Or go to **Actions → Run Agent Xpiper → Run workflow**.

### 5. Get your leads
Download the CSV from **Actions → your run → Artifacts**,
or find it committed in `data/leads/`.

---

## Local Development
```bash
pip install -r requirements.txt
cp .env.example .env
# fill in your keys in .env
python main.py
```

## Architecture
```
main.py
  └── ManagerAgent       (Groq #1 — llama-3.3-70b)
        ├── reads config/criteria.json
        ├── generates Zillow scraping plan
        └── generates qualification rules
  └── ScraperAgent       (Groq #2 — llama-3.1-70b + Jina AI)
        ├── fetches Zillow search pages via Jina
        ├── extracts agent profile links
        └── scrapes & structures each profile
  └── QualifierAgent     (Groq #3 — llama-3.3-70b)
        ├── scores each agent 0–100
        ├── applies hard disqualifiers
        └── returns only qualified leads
  └── csv_exporter
        └── data/leads/qualified_leads_TIMESTAMP.csv
```
