import logging
import math
import os
import requests

logger = logging.getLogger(__name__)

SERPAPI_BASE = "https://serpapi.com/search.json"


def get_serp_data(query: str, domain: str, location: str = "United States") -> dict:
    """
    Fetch Google SERP data for a query via SerpAPI.
    Returns domain position, SERP-derived difficulty, and estimated volume.

    Note: SerpAPI provides real SERP results and competitive signals.
    Search volume is estimated from total_results (SerpAPI has no keyword volume endpoint).
    """
    api_key = os.getenv("SERPAPI_KEY", "")
    try:
        params = {
            "q": query,
            "location": location,
            "hl": "en",
            "gl": "us",
            "num": 30,
            "api_key": api_key,
        }
        resp = requests.get(SERPAPI_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        domain_clean = domain.lower().replace("www.", "")
        organic = data.get("organic_results") or []

        serp_position = None
        for item in organic:
            link = (item.get("link") or "").lower()
            if domain_clean in link:
                serp_position = item.get("position") or item.get("rank_absolute")
                break

        total_results_raw = (data.get("search_information") or {}).get("total_results", 0)
        total_results = _parse_total_results(total_results_raw)

        ads = data.get("ads") or []
        knowledge_graph = data.get("knowledge_graph") or {}

        return {
            "domain_in_serp": serp_position is not None,
            "serp_position": serp_position,
            "competitive_difficulty": _estimate_difficulty(total_results, len(ads), bool(knowledge_graph)),
            "estimated_search_volume": _estimate_volume(total_results),
            "total_results": total_results,
            "ads_count": len(ads),
            "has_knowledge_graph": bool(knowledge_graph),
        }

    except Exception as e:
        logger.warning("SerpAPI call failed for query '%s': %s", query, e)
        return {
            "domain_in_serp": None,
            "serp_position": None,
            "competitive_difficulty": 50,
            "estimated_search_volume": 100,
            "total_results": 0,
            "ads_count": 0,
            "has_knowledge_graph": False,
        }


def _parse_total_results(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    try:
        digits = "".join(c for c in str(value) if c.isdigit())
        return int(digits) if digits else 0
    except Exception:
        return 0


def _estimate_difficulty(total_results: int, ads_count: int, has_knowledge_graph: bool) -> int:
    """
    Competitive difficulty (0–100) derived from SERP signals:
      - Base 70 pts from total result count on a log scale
      - Up to +20 pts from paid ads (commercial competition)
      - +10 pts if knowledge graph present (authoritative/branded topic)
    """
    if total_results <= 0:
        return 50
    log_val = math.log10(max(total_results, 1))
    base = min(log_val / math.log10(5_000_000_000) * 70, 70)
    ad_bonus = min(ads_count * 5, 20)
    kg_bonus = 10 if has_knowledge_graph else 0
    return min(int(base + ad_bonus + kg_bonus), 100)


def _estimate_volume(total_results: int) -> int:
    """
    Rough search volume proxy from total results count.
    SerpAPI does not expose keyword search volume; this is an estimate.
    Mapped on a log scale: ~100 results → ~100/mo, ~1B results → ~50,000/mo.
    """
    if total_results <= 0:
        return 100
    log_val = math.log10(max(total_results, 1))
    volume = int(100 * (10 ** (log_val / 10)))
    return min(max(volume, 100), 50_000)
