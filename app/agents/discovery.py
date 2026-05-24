import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI Visibility Research Specialist. Your job is to generate realistic, \
commercially relevant questions that users ask AI assistants (ChatGPT, Claude, Perplexity) \
when searching for products or services in a specific industry.

You must return ONLY valid JSON — no markdown, no explanation, no code fences.

Output schema:
{
  "queries": [
    {
      "query_text": "string — the full natural language question exactly as a user would type it",
      "query_type": "comparison | best_of | how_to | informational | pricing",
      "commercial_intent": "high | medium | low"
    }
  ]
}

Rules:
- Generate exactly 15 queries
- Mix query types: include comparison queries (X vs Y), best-of queries (best tool for X), \
how-to queries, pricing queries, and feature-specific queries
- Queries must sound like real questions typed into ChatGPT or Perplexity — conversational and specific
- Include queries that mention the target business by name and its competitors by name
- Include queries that do NOT mention any brand (generic industry queries)
- Do not include any text outside the JSON object
- Ensure query_text values are unique"""

USER_PROMPT_TEMPLATE = """Generate 15 AI assistant queries for this business:

Business Name: {name}
Domain: {domain}
Industry: {industry}
Description: {description}
Competitors: {competitors}

Focus on queries a real buyer or researcher would ask when comparing, evaluating, \
or looking for tools in the {industry} space. Include both branded and unbranded queries."""


class QueryDiscoveryAgent(BaseAgent):
    """Agent 1 — Discovers 15 commercially relevant AI search queries for a business profile."""

    def run(self, profile: dict) -> tuple[list[dict], int]:
        """
        Returns (queries, tokens_used).
        queries: list of dicts with query_text, query_type, commercial_intent
        """
        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile["name"],
            domain=profile["domain"],
            industry=profile["industry"],
            description=profile.get("description", ""),
            competitors=", ".join(profile.get("competitors", [])),
        )

        raw, tokens = self._chat(SYSTEM_PROMPT, user_prompt, temperature=0.7)
        parsed = self._parse_json(raw, fallback={"queries": []})

        queries = parsed.get("queries", [])
        if not isinstance(queries, list):
            logger.error("QueryDiscoveryAgent: 'queries' is not a list, got: %s", type(queries))
            queries = []

        validated = []
        for q in queries:
            if isinstance(q, dict) and q.get("query_text"):
                validated.append({
                    "query_text": str(q["query_text"]).strip(),
                    "query_type": q.get("query_type", "informational"),
                    "commercial_intent": q.get("commercial_intent", "medium"),
                })

        logger.info("QueryDiscoveryAgent: discovered %d queries using %d tokens", len(validated), tokens)
        return validated, tokens
