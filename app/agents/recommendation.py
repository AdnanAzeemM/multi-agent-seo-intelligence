import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an SEO Content Strategist specializing in AI visibility optimization. \
Your job is to generate specific, actionable content recommendations that will help a business \
appear in AI assistant answers (ChatGPT, Claude, Perplexity) for high-opportunity queries where \
they are currently NOT being mentioned.

You must return ONLY valid JSON — no markdown, no explanation, no code fences.

Output schema:
{
  "recommendations": [
    {
      "target_query_index": integer,
      "content_type": "blog_post | landing_page | faq | comparison_page | case_study | guide",
      "title": "string — specific, clickable content title (not generic)",
      "rationale": "string — 2-3 sentences explaining WHY this content closes the AI visibility gap",
      "target_keywords": ["string"],
      "priority": "high | medium | low",
      "estimated_word_count": integer
    }
  ]
}

Rules:
- Generate between 3 and 5 recommendations total
- target_query_index refers to the index (0-based) in the provided query list
- Titles must be specific and actionable — NOT generic (e.g. 'Frase vs Surfer SEO: Which Tool Wins for Content Teams in 2025?' NOT 'Comparison Article')
- target_keywords must contain 3–7 specific keyword phrases
- priority: high = opportunity_score >= 0.7, medium = 0.4–0.69, low = below 0.4
- Rationale must explain the AI visibility angle — why AI assistants would cite this content
- estimated_word_count: realistic target length (800–3000 words depending on content type)
- Do not include any text outside the JSON object"""

USER_PROMPT_TEMPLATE = """Generate content recommendations to improve AI visibility for this business:

Business: {name}
Domain: {domain}
Industry: {industry}

These are queries where {domain} has the most room to improve its AI assistant visibility (low opportunity score, weak visibility, or underperforming position):

{queries_list}

For each recommendation, specify which query it addresses via target_query_index (0-based). \
Focus on content that AI assistants are likely to reference when answering these queries — whether the goal is to first appear or to rank higher in AI answers."""


class ContentRecommendationAgent(BaseAgent):
    """Agent 3 — Generates 3–5 content recommendations for queries where the domain is not visible."""

    def run(
        self,
        profile: dict,
        target_queries: list[dict],
    ) -> tuple[list[dict], int]:
        """
        target_queries: list of {"query_text", "opportunity_score", "query_uuid"} — non-visible, sorted by score
        Returns (recommendations, tokens_used)
        """
        if not target_queries:
            return [], 0

        queries_list = "\n".join(
            f'{i}. "{q["query_text"]}" (opportunity_score: {q.get("opportunity_score", 0):.2f})'
            for i, q in enumerate(target_queries)
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile["name"],
            domain=profile["domain"],
            industry=profile["industry"],
            queries_list=queries_list,
        )

        raw, tokens = self._chat(SYSTEM_PROMPT, user_prompt, temperature=0.4)
        parsed = self._parse_json(raw, fallback={"recommendations": []})

        raw_recs = parsed.get("recommendations", [])
        if not isinstance(raw_recs, list):
            logger.error("ContentRecommendationAgent: 'recommendations' not a list")
            raw_recs = []

        recommendations = []
        for rec in raw_recs:
            if not isinstance(rec, dict):
                continue
            idx = rec.get("target_query_index", 0)
            query_uuid = target_queries[idx]["query_uuid"] if idx < len(target_queries) else None
            if not query_uuid:
                continue
            recommendations.append({
                "query_uuid": query_uuid,
                "content_type": rec.get("content_type", "blog_post"),
                "title": str(rec.get("title", "")).strip(),
                "rationale": str(rec.get("rationale", "")).strip(),
                "target_keywords": rec.get("target_keywords", []),
                "priority": rec.get("priority", "medium"),
                "estimated_word_count": rec.get("estimated_word_count"),
            })

        logger.info(
            "ContentRecommendationAgent: generated %d recommendations using %d tokens",
            len(recommendations),
            tokens,
        )
        return recommendations, tokens
