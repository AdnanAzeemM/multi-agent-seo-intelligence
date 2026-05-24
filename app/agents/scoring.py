import logging
from .base import BaseAgent
from ..utils.scoring import calculate_opportunity_score

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI Visibility Analyst. Your job is to assess whether a business domain \
would realistically be mentioned or recommended in an AI assistant's answer (ChatGPT, Claude, Perplexity) \
when a user asks a given question.

Important distinction: AI visibility is CORRELATED with but DIFFERENT from Google search rankings. \
AI assistants often cite well-known brands, comparison guides, and authoritative sources regardless \
of their exact Google position. A domain at position 8 in Google may still appear prominently in \
AI answers if it is a recognised brand in that space.

You will be given real Google SERP context from SerpAPI to inform your assessment.

You must return ONLY valid JSON — no markdown, no explanation, no code fences.

Output schema:
{
  "domain_visible": true | false,
  "visibility_position": integer or null,
  "visibility_reasoning": "string — 2 sentences: why the domain would or would not appear in an AI answer",
  "visibility_confidence": "high | medium | low"
}

Rules:
- domain_visible: true if the domain would likely be named in a typical AI assistant answer
- visibility_position: 1–10 if visible (1 = mentioned first, 10 = briefly mentioned near end), null if not visible
- Use the SERP context to calibrate: if the domain doesn't appear in Google top 30, it is unlikely to \
  appear in AI answers unless it is a well-known brand
- visibility_confidence reflects how certain you are given the available context
- Do not include any text outside the JSON object"""

USER_PROMPT_TEMPLATE = """Assess AI assistant visibility for this business:

Query: "{query_text}"
Target Domain: {domain}
Industry: {industry}
Competitors in this space: {competitors}

Real Google SERP data (from SerpAPI):
- Domain found in top 30 Google organic results: {domain_in_serp}
- Domain's Google organic position: {serp_position}
- Competing pages indexed by Google: {total_results:,}
- Paid ads on this SERP: {ads_count}
- Knowledge graph present: {has_knowledge_graph}

Given this real search data, would {domain} be mentioned or recommended in a ChatGPT or Perplexity \
answer to the query above? Consider brand recognition, relevance, and whether the query invites \
tool/product recommendations."""


class VisibilityScoringAgent(BaseAgent):
    """
    Agent 2 — Scores each query using:
    - Real Google SERP data from SerpAPI (domain position, difficulty, volume estimate)
    - GPT-4o to assess AI assistant visibility (ChatGPT/Perplexity, distinct from Google ranking)
    """

    def run(
        self,
        query_text: str,
        domain: str,
        industry: str,
        competitors: list[str],
        serp_data: dict,
    ) -> tuple[dict, int]:
        """
        serp_data: output from utils.serpapi.get_serp_data()
        Returns (scored_result, tokens_used)
        """
        search_volume = serp_data.get("estimated_search_volume", 100)
        competitive_difficulty = serp_data.get("competitive_difficulty", 50)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            query_text=query_text,
            domain=domain,
            industry=industry,
            competitors=", ".join(competitors) if competitors else "none specified",
            domain_in_serp=serp_data.get("domain_in_serp", "unknown"),
            serp_position=serp_data.get("serp_position") or "not found",
            total_results=serp_data.get("total_results", 0),
            ads_count=serp_data.get("ads_count", 0),
            has_knowledge_graph=serp_data.get("has_knowledge_graph", False),
        )

        raw, tokens = self._chat(SYSTEM_PROMPT, user_prompt, temperature=0.2)
        parsed = self._parse_json(raw, fallback={
            "domain_visible": False,
            "visibility_position": None,
            "visibility_reasoning": "Unable to assess — LLM parse error",
            "visibility_confidence": "low",
        })

        domain_visible = parsed.get("domain_visible", False)
        visibility_position = parsed.get("visibility_position")

        opportunity_score = calculate_opportunity_score(
            search_volume=search_volume,
            competitive_difficulty=competitive_difficulty,
            domain_visible=domain_visible,
            visibility_position=visibility_position,
            query_text=query_text,
        )

        result = {
            "estimated_search_volume": search_volume,
            "competitive_difficulty": competitive_difficulty,
            "domain_visible": domain_visible,
            "visibility_position": visibility_position,
            "visibility_reasoning": parsed.get("visibility_reasoning", ""),
            "visibility_confidence": parsed.get("visibility_confidence", "low"),
            "opportunity_score": opportunity_score,
        }

        logger.info(
            "VisibilityScoringAgent: query='%s' serp_pos=%s ai_visible=%s score=%.3f tokens=%d",
            query_text[:60],
            serp_data.get("serp_position"),
            domain_visible,
            opportunity_score,
            tokens,
        )
        return result, tokens
