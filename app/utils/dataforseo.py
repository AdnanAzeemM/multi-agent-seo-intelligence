import base64
import logging
import os
import requests

logger = logging.getLogger(__name__)

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"


def _get_auth_header() -> dict:
    login = os.getenv("DATAFORSEO_LOGIN", "")
    password = os.getenv("DATAFORSEO_PASSWORD", "")
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def get_keyword_data(keywords: list[str], location: str = "United States", language: str = "en") -> dict[str, dict]:
    """
    Fetch search volume and keyword difficulty for a list of keywords.
    Returns a dict keyed by keyword with volume + difficulty.
    Falls back to safe defaults on any failure.
    """
    result = {kw: {"search_volume": 100, "keyword_difficulty": 50} for kw in keywords}

    try:
        volumes = _fetch_search_volumes(keywords, location, language)
        for kw, vol in volumes.items():
            result[kw]["search_volume"] = vol
    except Exception as e:
        logger.warning("DataForSEO search volume fetch failed: %s", e)

    try:
        difficulties = _fetch_keyword_difficulties(keywords, location, language)
        for kw, diff in difficulties.items():
            result[kw]["keyword_difficulty"] = diff
    except Exception as e:
        logger.warning("DataForSEO keyword difficulty fetch failed: %s", e)

    return result


def _fetch_search_volumes(keywords: list[str], location: str, language: str) -> dict[str, int]:
    payload = [{"keywords": keywords, "location_name": location, "language_code": language}]
    resp = requests.post(
        f"{DATAFORSEO_BASE}/keywords_data/google_ads/search_volume/live",
        headers=_get_auth_header(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    volumes: dict[str, int] = {}
    for task in data.get("tasks", []):
        for item in (task.get("result") or []):
            kw = item.get("keyword", "")
            vol = item.get("search_volume") or 0
            if kw:
                volumes[kw] = vol
    return volumes


def _fetch_keyword_difficulties(keywords: list[str], location: str, language: str) -> dict[str, int]:
    payload = [{"keywords": keywords, "location_name": location, "language_code": language}]
    resp = requests.post(
        f"{DATAFORSEO_BASE}/dataforseo_labs/google/bulk_keyword_difficulty/live",
        headers=_get_auth_header(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    difficulties: dict[str, int] = {}
    for task in data.get("tasks", []):
        for item in (task.get("result") or []):
            for kw_item in item.get("items") or []:
                kw = kw_item.get("keyword", "")
                diff = kw_item.get("keyword_difficulty") or 50
                if kw:
                    difficulties[kw] = int(diff)
    return difficulties


def check_domain_in_serp(query: str, domain: str, location: str = "United States", language: str = "en") -> dict:
    """
    Check if domain appears in Google organic results for the query.
    Returns position (1-based) or None if not found.
    """
    try:
        payload = [{"keyword": query, "location_name": location, "language_code": language, "depth": 30}]
        resp = requests.post(
            f"{DATAFORSEO_BASE}/serp/google/organic/live/advanced",
            headers=_get_auth_header(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for task in data.get("tasks", []):
            for result in task.get("result") or []:
                for item in result.get("items") or []:
                    url = item.get("url", "") or ""
                    rank = item.get("rank_absolute")
                    if domain.lower().replace("www.", "") in url.lower():
                        return {"found": True, "position": rank}
        return {"found": False, "position": None}
    except Exception as e:
        logger.warning("DataForSEO SERP check failed for '%s': %s", query, e)
        return {"found": None, "position": None}
