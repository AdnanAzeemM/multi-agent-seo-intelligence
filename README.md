# AI Visibility Intelligence API

A RESTful Flask API that helps businesses discover how they appear in AI-generated answers (ChatGPT, Claude, Perplexity) and generates actionable content recommendations to improve that visibility.

---

## Quick Start

### Option A — Docker Compose (recommended)

```bash
git clone <repo-url>
cd multi-agent-seo-intelligence

cp .env.example .env
# Fill in OPENAI_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD in .env

docker-compose up --build
```

API will be available at `http://localhost:5000`.

### Option B — Local Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your credentials in .env (PostgreSQL DATABASE_URL, OpenAI, SerpAPI)

flask db upgrade
flask run
```

### Run Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o) |
| `SERPAPI_KEY` | SerpAPI key for real SERP data |
| `DATABASE_URL` | PostgreSQL connection string |
| `FLASK_ENV` | `development` or `production` |
| `SECRET_KEY` | Flask secret key |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/profiles` | Register a business profile |
| GET | `/api/v1/profiles/{uuid}` | Get profile + summary stats |
| POST | `/api/v1/profiles/{uuid}/run` | Trigger the 3-agent pipeline |
| GET | `/api/v1/profiles/{uuid}/queries` | List discovered queries |
| GET | `/api/v1/profiles/{uuid}/recommendations` | List content recommendations |
| POST | `/api/v1/queries/{uuid}/recheck` | Re-score a single query |

### Example Flow

```bash
# 1. Register a profile
curl -X POST http://localhost:5000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Frase",
    "domain": "frase.io",
    "industry": "SEO Content Tools",
    "description": "AI-powered content briefs",
    "competitors": ["surferseo.com", "marketmuse.com"]
  }'

# 2. Run the pipeline (takes 15–30 seconds)
curl -X POST http://localhost:5000/api/v1/profiles/{uuid}/run

# 3. Get high-opportunity queries
curl "http://localhost:5000/api/v1/profiles/{uuid}/queries?min_score=0.6"

# 4. Get recommendations
curl http://localhost:5000/api/v1/profiles/{uuid}/recommendations
```

---

## Architecture

```
POST /profiles/{uuid}/run
        │
        ▼
  Pipeline Orchestrator (services/pipeline.py)
        │
        ├── Agent 1: QueryDiscoveryAgent
        │     └── GPT-4o generates 15 AI search queries
        │
        ├── SerpAPI (per query) — real SERP data, domain position, difficulty
        │
        ├── Agent 2: VisibilityScoringAgent (per query, failures skipped)
        │     └── GPT-4o simulates AI assistant visibility
        │     └── Opportunity score calculated
        │
        └── Agent 3: ContentRecommendationAgent
              └── GPT-4o generates 3–5 content recommendations
```

### Agent Design Rationale

**Why GPT-4o for all agents?**  
GPT-4o with `response_format: json_object` produces reliable structured output. Its broad training data makes it well-suited for simulating AI visibility (Agent 2) — it approximates what another LLM would reference when answering user queries. A single provider is used across all agents to simplify token tracking, reduce latency, and keep the integration surface minimal.

**Agent separation:**  
Each agent is an independent class with its own system prompt, user prompt template, and output validation. The orchestrator calls them in sequence and handles partial failures — if Agent 2 fails for one query, processing continues for the rest. Agents share only a `BaseAgent` with the OpenAI client and JSON parsing logic.

**SerpAPI integration:**  
After Agent 1 discovers queries, each query is checked against SerpAPI's Google organic search (`/search.json`). This returns real SERP data: domain position in top 30 organic results, total competing pages, and ad presence. Competitive difficulty and estimated search volume are derived from these signals (see formula below). SerpAPI does not provide keyword search volume directly — volume is estimated from `total_results` on a log scale and clearly documented as an estimate. If SerpAPI fails for a query, safe defaults are used so the pipeline continues.

---

## Opportunity Score Formula

**Score = (Volume × 0.35) + (Ease × 0.25) + (Visibility Gap × 0.25) + (Intent × 0.15)**

All factors normalized to [0.0, 1.0]. Final score clamped to [0.0, 1.0].

| Factor | Weight | Calculation |
|---|---|---|
| **Volume Score** | 35% | `min(search_volume / 10_000, 1.0)` |
| **Ease Score** | 25% | `1.0 - (competitive_difficulty / 100)` |
| **Visibility Gap** | 25% | `1.0` if not visible · `0.5` if visible but position > 5 · `0.1` if well-ranked |
| **Commercial Intent** | 15% | `1.0` for comparison/best-of · `0.6` for how-to/tool · `0.3` for informational |

**Reasoning:**  
Volume is the largest weight (35%) because traffic potential is the primary business value driver. Ease (25%) captures competitive opportunity — a low-difficulty keyword is an easier win. Visibility Gap (25%) ensures not-appearing queries are prioritized — that's the core gap this tool addresses. Intent (15%) up-weights commercial queries that drive conversions, matching how real SEO teams prioritize content.

**Example:**  
"Frase vs Surfer SEO" with volume=8000, difficulty=35, not visible, contains "vs":  
`(0.80 × 0.35) + (0.65 × 0.25) + (1.0 × 0.25) + (1.0 × 0.15) = 0.28 + 0.16 + 0.25 + 0.15 = 0.84`

---

## Data Model Decisions

- **UUID primary keys** on all tables for API safety and future distributed use
- **`competitors` stored as JSON column** — list of domain strings, simple and queryable
- **`DiscoveredQuery` links to both `profile_uuid` and `run_uuid`** — enables per-run filtering and also profile-wide query history
- **`ContentRecommendation` links to `run_uuid`** — tracks which pipeline run produced each recommendation, useful for A/B comparison across runs
- **`visibility_reasoning` and `visibility_confidence` stored** — gives the end user explainability for why a domain is or isn't visible
- **`last_checked_at` separate from `discovered_at`** — enables tracking recheck history

---


